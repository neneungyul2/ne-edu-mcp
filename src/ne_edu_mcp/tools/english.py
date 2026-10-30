"""영어 학원·교습소 판정 도구: 시군구별 집계(JSON)와 엑셀/CSV 내보내기."""
import json
from typing import Annotated

from pydantic import Field

from ..academy import AcademyService, build_predicate
from ..client import ApiError
from ..english import (
    CRITERIA, EX_STALE, LANG, TUTOR, classify, region, sido_rank, tally, with_ratios,
)
from ..export import Sheet, export_sheets
from ..offices import OFFICES, resolve_office
from ..tool_filter import ToolRegistrar
from .academy import NO_KEY_NOTICE, export_dir

OFFICE_SCAN_CAP = 80_000  # 교육청 하나(경기 약 4만 곳)를 끝까지 훑는 한도

COUNT_COLUMNS = (
    ("학원_어학원", "학원: 어학원 (개)"), ("학원_보습영어", "학원: 보습 영어 (개)"), ("학원_계", "학원: 계 (개)"),
    ("교습소_외국어", "교습소: 외국어 (개)"), ("교습소_보습영어", "교습소: 보습 영어 (개)"), ("교습소_계", "교습소: 계 (개)"),
    ("합계", "합계 (개)"),
    ("어학원_비중", "비중: 어학원 (%)"), ("학원중_어학원_비중", "비중: 학원 중 어학원 (%)"),
    ("어학원계열_비중", "비중: 어학원 계열 (%)"),
    ("전체_학원", "참고: 전체 학원 (개)"), ("전체_교습소", "참고: 전체 교습소 (개)"),
)
LIST_COLUMNS = (
    "학원명", "분야", "교습계열", "교습과정", "교습과정목록", "정원합계", "일시수용능력인원",
    "설립일", "도로명주소", "상세주소", "전화번호", "학원지정번호", "시도교육청",
)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def _collect_office(service: AcademyService, office: str) -> list[dict]:
    params = {"ATPT_OFCDC_SC_CODE": resolve_office(office).code}
    done = await service.collect(
        params, build_predicate(None, "개원", None), want=OFFICE_SCAN_CAP, scan_cap=OFFICE_SCAN_CAP
    )
    if not done.exhausted:
        raise ApiError(f"{resolve_office(office).name}을(를) 끝까지 훑지 못했습니다 ({done.scanned}/{done.total}건).")
    return done.rows


def judge(rows: list[dict], seen: set | None = None) -> list[dict]:
    """행마다 _시도·_시군구·_분류·_비고를 붙인다. seen으로 교육청 간 중복을 거른다."""
    seen = set() if seen is None else seen
    out = []
    for row in rows:
        key = (row.get("학원지정번호"), row.get("학원명"))
        if key in seen:
            continue
        seen.add(key)
        where = region(row)
        verdict = classify(row)
        notes = []
        if verdict.order_missing and verdict.category in (LANG, TUTOR):
            notes.append("계열 미기재")
        if verdict.lang_named_tutor and row.get("구분") == "학원":
            notes.append("이름이 어학원")
        out.append({
            **row,
            "_시도": where[0] if where else None,
            "_시군구": where[1] if where else None,
            "_분류": verdict.category if where else (EX_STALE if verdict.category else None),
            "_비고": ", ".join(notes) or None,
        })
    return out


def _count_row(c: dict) -> list:
    r = with_ratios(c)
    return [r[k] for k, _ in COUNT_COLUMNS]


def register_english_tools(registrar: ToolRegistrar, service: AcademyService | None) -> None:
    async def count_english_academies(
        office: Annotated[str, Field(description="시도교육청: 줄임말(서울, 경기), 코드(B10), 전체 이름")],
        sgg: Annotated[str | None, Field(description="시군구 이름(주소 기준, 예: 수원시, 강남구). 비우면 시도 전체")] = None,
    ) -> str:
        if not service.client.has_key:
            raise ApiError(f"집계에는 인증키가 필요합니다. {NO_KEY_NOTICE}")
        rows = judge(await _collect_office(service, office))
        by_sido, by_sgg = tally(rows)
        items = [
            {"시도": k[0], "시군구": k[1], **with_ratios(v)}
            for k, v in sorted(by_sgg.items(), key=lambda kv: (sido_rank(kv[0][0]), -kv[1]["학원_어학원"]))
            if not sgg or k[1] == sgg.strip()
        ]
        if sgg and not items:
            raise ValueError(f"{sgg!r} 시군구를 찾지 못했습니다. 주소 기준 이름(예: 수원시, 강남구)으로 넣으세요.")
        return _dump({
            "기준": [{"항목": k, "내용": v} for k, v in CRITERIA],
            "시도별": {k: with_ratios(v) for k, v in by_sido.items()},
            "시군구별": items,
        })

    async def export_english_academies(
        offices: Annotated[
            list[str] | None, Field(description="시도교육청 목록(예: ['서울','경기']). 비우면 전국 17곳")
        ] = None,
        file_name: Annotated[str | None, Field(description="저장할 파일 이름(확장자 제외). 기본: 영어학원_현황_전국")] = None,
    ) -> str:
        if not service.client.has_key:
            raise ApiError(f"내보내기에는 인증키가 필요합니다. {NO_KEY_NOTICE}")
        targets = [resolve_office(o) for o in offices] if offices else list(OFFICES)
        seen: set = set()
        rows: list[dict] = []
        for o in targets:
            rows += judge(await _collect_office(service, o.code), seen)
        by_sido, by_sgg = tally(rows)

        names = [label for _, label in COUNT_COLUMNS]
        sido_rows = [[s, *_count_row(c)] for s, c in sorted(by_sido.items(), key=lambda kv: sido_rank(kv[0]))]
        total = {k: sum(c[k] for c in by_sido.values()) for k in next(iter(by_sido.values()), {})}
        if total:
            sido_rows.append(["전국", *_count_row(total)])
        sgg_rows = [
            [k[0], k[1], *_count_row(c)]
            for k, c in sorted(by_sgg.items(), key=lambda kv: (sido_rank(kv[0][0]), -(kv[1]["학원_어학원"] + kv[1]["교습소_외국어"])))
        ]

        def listing(pred) -> list[list]:
            sel = sorted(
                (r for r in rows if pred(r.get("_분류"))),
                key=lambda r: (sido_rank(r["_시도"] or ""), r["_시군구"] or "", r.get("구분") != "학원", r.get("학원명") or ""),
            )
            return [[r["_시도"], r["_시군구"], r.get("구분"), r["_분류"], r["_비고"], *[r.get(c) for c in LIST_COLUMNS]] for r in sel]

        head = ["시도", "시군구", "구분", "분류", "비고", *LIST_COLUMNS]
        sheets = [
            Sheet("기준", ["항목", "내용"], [list(x) for x in CRITERIA]),
            Sheet("시도별", ["시도", *names], sido_rows),
            Sheet("시군구별", ["시도", "시군구", *names], sgg_rows),
            Sheet("명단", head, listing(lambda c: c in (LANG, TUTOR))),
            Sheet("제외_명단", head, listing(lambda c: bool(c) and c.startswith("제외"))),
        ]
        base = file_name or ("영어학원_현황_전국" if not offices else "영어학원_현황_" + "_".join(o.short for o in targets))
        result = export_sheets(sheets, export_dir(), base)
        return _dump({**result.to_dict(), "전국": with_ratios(total) if total else None, "시군구": len(sgg_rows)})

    registrar.register(
        "count_english_academies",
        count_english_academies,
        "시도교육청 하나의 영어 학원·교습소를 정해진 기준으로 판정해 시군구별로 센다 "
        "(학원: 어학원·보습 영어 / 교습소: 외국어·보습 영어 / 어학원 비중). 인증키가 필요하다. "
        "판정 기준은 결과의 '기준'에 있다. 여러 시도·전국이나 명단이 필요하면 export_english_academies를 쓴다.",
    )
    registrar.register(
        "export_english_academies",
        export_english_academies,
        "영어 어학원·보습 영어학원·영어 교습소를 정해진 기준으로 판정해 시도별·시군구별 집계와 명단을 엑셀(xlsx)·CSV로 저장한다. "
        "offices를 비우면 전국. 성인 어학·영어 외 외국어·원격학원·다른 과목 이름의 등록 오류는 제외 명단으로 따로 둔다. 인증키가 필요하다.",
    )
