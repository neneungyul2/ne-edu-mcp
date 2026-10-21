"""학교알리미 도구: 공시 항목·지역 안내, 공시정보 조회, 엑셀/CSV 내보내기."""
import json
from typing import Annotated

from pydantic import Field

from ..export import Sheet, export_sheets
from ..school_service import SchoolDisclosureService, resolve_fields, shape_rows
from ..schoolinfo import (
    SCHOOL_KINDS,
    find_item,
    items,
    regions,
    resolve_school_kind,
    resolve_sggs,
    resolve_sido,
)
from ..tool_filter import ToolRegistrar
from .academy import export_dir

MAX_EXPORT_ROWS = 100_000

ItemArg = Annotated[str, Field(description="공시 항목: apiType 번호(62)나 이름(학교 현황). list_school_disclosure_items 참고")]
SidoArg = Annotated[str, Field(description="시도: 줄임말(서울, 경기), 이름, 코드(11). 광주·전남은 전남광주통합특별시(12)")]
SggArg = Annotated[str | None, Field(description="시군구 이름(종로구) 또는 코드. 비우면 시도 전체. 수원시처럼 구가 있는 시는 하위 구를 모두 포함")]
NameArg = Annotated[str | None, Field(description="학교명에 포함된 글자. 예: 한국")]
FieldsArg = Annotated[
    list[str] | None,
    Field(description="출력할 필드(항목명 또는 필드 ID). 비우면 지역 메타를 뺀 전체. 학교명·학교코드는 항상 포함. describe_school_disclosure_item 참고"),
]


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def register_school_tools(registrar: ToolRegistrar, service: SchoolDisclosureService | None) -> None:
    async def list_school_disclosure_items(
        query: Annotated[str | None, Field(description="항목 이름에 포함된 글자로 거른다. 예: 학생수")] = None,
    ) -> str:
        found = [i for i in items() if not query or query.strip() in i.name]
        return _dump([{"apiType": i.api_type, "항목": i.name, "필드수": len(i.fields)} for i in found])

    async def describe_school_disclosure_item(item: ItemArg) -> str:
        it = find_item(item)
        keys = it.keys()
        return _dump({
            "apiType": it.api_type,
            "항목": it.name,
            "필드": [
                {"id": f.id, "이름": keys[f.id], "학교급": f.levels, **({"구분": f.section} if f.section else {})}
                for f in it.fields
            ],
        })

    async def list_school_regions(
        sido: Annotated[str | None, Field(description="시도. 비우면 시도 목록, 지정하면 그 시도의 시군구 목록")] = None,
    ) -> str:
        if not sido:
            return _dump({
                "시도": [{"코드": s.code, "이름": s.name, "시군구수": len(s.sgg)} for s in regions()],
                "학교급": [{"코드": c, "이름": n} for c, n in SCHOOL_KINDS.items()],
            })
        s = resolve_sido(sido)
        return _dump({"시도": {"코드": s.code, "이름": s.name}, "시군구": [{"코드": g.code, "이름": g.name} for g in s.sgg]})

    async def get_school_disclosure(
        item: ItemArg,
        sido: SidoArg,
        school_kind: Annotated[str, Field(description="학교급: 초등, 중학교, 고등, 특수, 그외, 각종 또는 코드(02~07)")],
        sgg: SggArg = None,
        school_name: NameArg = None,
        fields: FieldsArg = None,
        limit: Annotated[int, Field(ge=1, le=200, description="최대 학교 수 (기본 20, 최대 200)")] = 20,
    ) -> str:
        it = find_item(item)
        sido_info = resolve_sido(sido)
        sggs = resolve_sggs(sido_info, sgg)
        kind = resolve_school_kind(school_kind)
        field_ids = resolve_fields(it, fields)
        rows = await service.fetch(it, sido_info, sggs, [kind], school_name=school_name)
        shown = shape_rows(it, rows[:limit], field_ids)
        out = {
            "항목": it.name,
            "시도": sido_info.name,
            "학교급": SCHOOL_KINDS[kind],
            "시군구수": len(sggs),
            "전체_건수": len(rows),
            "반환_건수": len(shown),
            "items": shown,
        }
        if len(rows) > limit:
            out["note"] = f"{len(rows)}건 중 {limit}건만 보여줍니다. 전체는 export_school_disclosure로 저장하세요."
        return _dump(out)

    async def export_school_disclosure(
        item: ItemArg,
        sido: SidoArg,
        school_kinds: Annotated[list[str] | None, Field(description="학교급 목록. 비우면 초·중·고·특수·그외·각종 전체")] = None,
        sgg: SggArg = None,
        school_name: NameArg = None,
        fields: FieldsArg = None,
        file_name: Annotated[str | None, Field(description="저장할 파일 이름(확장자 제외). 기본: 학교알리미_항목_시도")] = None,
    ) -> str:
        it = find_item(item)
        sido_info = resolve_sido(sido)
        sggs = resolve_sggs(sido_info, sgg)
        kinds = [resolve_school_kind(k) for k in school_kinds] if school_kinds else list(SCHOOL_KINDS)
        field_ids = resolve_fields(it, fields)
        rows = await service.fetch(it, sido_info, sggs, kinds, school_name=school_name)
        truncated = len(rows) > MAX_EXPORT_ROWS
        shaped = shape_rows(it, rows[:MAX_EXPORT_ROWS], field_ids)
        columns = list(shaped[0]) if shaped else [it.keys()[i] for i in field_ids]
        sheet = Sheet(it.name, columns, [[r.get(c) for c in columns] for r in shaped])
        base = file_name or f"학교알리미_{it.name}_{sido_info.name}"
        result = export_sheets([sheet], export_dir(), base)
        out = {**result.to_dict(), "rows": len(shaped), "시군구수": len(sggs), "학교급": [SCHOOL_KINDS[k] for k in kinds]}
        if truncated:
            out["note"] = f"{MAX_EXPORT_ROWS}건에서 잘렸습니다. 조건을 좁히세요."
        return _dump(out)

    registrar.register(
        "list_school_disclosure_items",
        list_school_disclosure_items,
        "학교알리미(schoolinfo.go.kr) OpenAPI가 제공하는 공시 항목 35종(학교 현황, 성별 학생수, 교원 현황, 급식, 방과후학교, 교복 단가 등)과 apiType 번호를 보여준다. 인증키 없이 쓸 수 있다.",
    )
    registrar.register(
        "describe_school_disclosure_item",
        describe_school_disclosure_item,
        "공시 항목 하나의 출력 필드(이름, ID, 해당 학교급)를 보여준다. get_school_disclosure의 fields를 정할 때 쓴다.",
    )
    registrar.register(
        "list_school_regions",
        list_school_regions,
        "학교알리미 시도·시군구 코드와 학교급 코드를 보여준다. 광주와 전남은 공식 코드표에서 전남광주통합특별시(12)로 합쳐져 있다.",
    )
    registrar.register(
        "get_school_disclosure",
        get_school_disclosure,
        "학교알리미 공시정보를 조회한다: 시도(필수)·시군구·학교급(필수) 범위의 학교별 값을 학교명으로 거르고 필요한 필드만 골라 돌려준다. "
        "인증키(SCHOOLINFO_API_KEY)가 필요하다. 시군구를 비우면 시도 안의 모든 시군구를 호출하므로 학교명이나 시군구로 좁히는 편이 빠르다. "
        "학교알리미는 최근 3년 자료만 공시한다.",
    )
    registrar.register(
        "export_school_disclosure",
        export_school_disclosure,
        "학교알리미 공시정보를 시도(또는 시군구)·학교급 범위로 모두 모아 엑셀(xlsx)과 CSV로 저장하고 파일 경로를 돌려준다. 인증키(SCHOOLINFO_API_KEY)가 필요하다. "
        "저장 폴더는 NEIS_EXPORT_DIR 환경변수(기본: 작업 폴더의 exports).",
    )
