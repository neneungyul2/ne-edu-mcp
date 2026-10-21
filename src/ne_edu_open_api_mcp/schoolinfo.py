"""학교알리미 OpenAPI: 항목 카탈로그, 지역 코드, 클라이언트.

항목(apiType)과 출력 필드, 시도/시군구 코드는 학교알리미 공식 엑셀에서 만든 data/*.json에서 읽는다
(scripts/build_schoolinfo_data.py). 호출 형식은 학교알리미 OpenAPI 개발자 가이드를 따른다:
https://www.schoolinfo.go.kr/openApi.do?apiKey=..&apiType=..&sidoCode=..&sggCode=..&schulKndCode=..
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

import httpx

from .client import ApiError

OPEN_API_URL = "https://www.schoolinfo.go.kr/openApi.do"
KEY_HINT = (
    "SCHOOLINFO_API_KEY가 올바른지 확인하세요 "
    "(https://www.schoolinfo.go.kr > OpenAPI > API 이용안내에서 SNS 로그인 후 인증키 발급)."
)

SCHOOL_KINDS: dict[str, str] = {
    "02": "초등학교",
    "03": "중학교",
    "04": "고등학교",
    "05": "특수학교",
    "06": "그외학교",
    "07": "각종학교",
}

# 줄임말 → 시도코드. 광주는 공식 코드표에서 전남과 함께 12(전남광주통합특별시)로 통합되어 있다.
SIDO_ALIASES: dict[str, str] = {
    "서울": "11", "전남광주": "12", "광주": "12", "전남": "12", "전라남도": "12", "광주광역시": "12",
    "부산": "26", "대구": "27", "인천": "28", "대전": "30", "울산": "31", "세종": "36",
    "경기": "41", "충북": "43", "충남": "44", "경북": "47", "경남": "48", "제주": "50",
    "강원": "51", "전북": "52",
}

# 학교 기본정보에서 시도/지역 메타로 항상 같은 값이 반복되는 필드 (기본 출력에서 뺀다)
META_IDS = frozenset({
    "ATPT_OFCDC_ORG_NM", "ATPT_OFCDC_ORG_CODE", "JU_ORG_NM", "JU_ORG_CODE",
    "ADRCD_NM", "ADRCD_CD", "LCTN_SC_CODE",
})
SCHOOL_NAME_ID = "SCHUL_NM"
SCHOOL_CODE_ID = "SCHUL_CODE"


@dataclass(frozen=True)
class Field:
    id: str
    label: str
    levels: str
    section: str | None = None


@dataclass(frozen=True)
class Item:
    api_type: str
    name: str
    fields: tuple[Field, ...]

    def keys(self) -> dict[str, str]:
        """필드 ID → 결과에서 쓸 이름. 항목명이 겹치면 구분(세입/세출 등)이나 ID를 붙여 구별한다."""
        counts: dict[str, int] = {}
        for f in self.fields:
            counts[f.label] = counts.get(f.label, 0) + 1
        out: dict[str, str] = {}
        used: set[str] = set()
        for f in self.fields:
            key = f.label
            if counts[f.label] > 1:
                key = f"{f.section}.{f.label}" if f.section else f"{f.label}({f.id})"
            if key in used:
                key = f"{f.label}({f.id})"
            used.add(key)
            out[f.id] = key
        return out


@dataclass(frozen=True)
class Sgg:
    code: str
    name: str


@dataclass(frozen=True)
class Sido:
    code: str
    name: str
    sgg: tuple[Sgg, ...]


def _data(name: str) -> Any:
    text = resources.files("ne_edu_open_api_mcp").joinpath("data", name).read_text(encoding="utf-8")
    return json.loads(text)


@lru_cache(maxsize=1)
def items() -> tuple[Item, ...]:
    return tuple(
        Item(i["api_type"], i["name"], tuple(Field(f["id"], f["label"], f["levels"], f.get("section")) for f in i["fields"]))
        for i in _data("schoolinfo_items.json")
    )


@lru_cache(maxsize=1)
def regions() -> tuple[Sido, ...]:
    return tuple(
        Sido(r["code"], r["name"], tuple(Sgg(g["code"], g["name"]) for g in r["sgg"]))
        for r in _data("schoolinfo_regions.json")
    )


def find_item(query: str | int) -> Item:
    """apiType 번호('62', 0), 항목 이름, 이름의 일부(하나로 정해질 때)로 찾는다."""
    text = str(query).strip()
    if not text:
        raise ValueError("공시 항목을 지정하세요. list_school_disclosure_items로 목록을 볼 수 있습니다.")
    for it in items():
        if text == it.api_type or text == it.name:
            return it
    if text.isdigit():  # '8' → '08' 같은 입력
        for it in items():
            if it.api_type.isdigit() and int(it.api_type) == int(text):
                return it
    matches = [it for it in items() if text in it.name]
    if len(matches) == 1:
        return matches[0]
    if matches:
        names = ", ".join(f"{m.name}({m.api_type})" for m in matches)
        raise ValueError(f"{text!r}에 해당하는 항목이 여러 개입니다: {names}")
    raise ValueError(f"알 수 없는 공시 항목: {text!r}. list_school_disclosure_items로 목록을 확인하세요.")


def resolve_sido(value: str) -> Sido:
    """시도코드('11'), 이름('서울특별시'), 줄임말('서울')."""
    text = (value or "").strip()
    for s in regions():
        if text in (s.code, s.name):
            return s
    code = SIDO_ALIASES.get(text)
    if code is None:
        code = next((c for alias, c in SIDO_ALIASES.items() if text.startswith(alias)), None)
    if code is not None:
        return next(s for s in regions() if s.code == code)
    valid = ", ".join(f"{s.name}({s.code})" for s in regions())
    raise ValueError(f"알 수 없는 시도: {text!r}. 가능한 값: {valid}")


def resolve_sggs(sido: Sido, value: str | None) -> list[Sgg]:
    """시군구. 지정하지 않으면 시도의 전체. '수원시'처럼 구가 나뉜 시는 하위 구를 모두 돌려준다."""
    text = (value or "").strip()
    if not text:
        return list(sido.sgg)
    exact = [g for g in sido.sgg if text in (g.code, g.name)]
    if exact:
        return exact
    partial = [g for g in sido.sgg if g.name.startswith(text) or text in g.name]
    if partial:
        return partial
    sample = ", ".join(g.name for g in sido.sgg[:8])
    raise ValueError(f"{sido.name}에서 시군구 {text!r}을(를) 찾을 수 없습니다. 예: {sample} ... (list_school_regions로 확인)")


def resolve_school_kind(value: str) -> str:
    """학교급 코드('02'), 이름('초등학교'), 줄임말('초등', '초')."""
    text = (value or "").strip()
    if text in SCHOOL_KINDS:
        return text
    for code, name in SCHOOL_KINDS.items():
        if text in (name, name.removesuffix("학교")) or (text and name.startswith(text)):
            return code
    valid = ", ".join(f"{n}({c})" for c, n in SCHOOL_KINDS.items())
    raise ValueError(f"알 수 없는 학교급: {text!r}. 가능한 값: {valid}")


def parse_response(body: Any) -> list[dict]:
    """학교알리미 응답 {"resultCode","resultMsg","list"}에서 행 목록을 꺼낸다. 실패 응답은 ApiError."""
    if not isinstance(body, dict) or "resultCode" not in body:
        raise ApiError(f"[학교알리미] 예상하지 못한 응답 형식입니다: {str(body)[:200]}")
    if body["resultCode"] != "success":
        message = body.get("resultMsg") or "원인 불명"
        hint = f" {KEY_HINT}" if "apiKey" in message else ""
        raise ApiError(f"[학교알리미] {message}{hint}")
    rows = body.get("list")
    return rows if isinstance(rows, list) else []


class SchoolInfoClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(transport=transport, timeout=timeout)

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def disclosure(self, api_type: str, sido_code: str, sgg_code: str, school_kind: str) -> list[dict]:
        """한 시군구, 한 학교급의 공시정보 행들."""
        if not self._key:
            raise ApiError(f"학교알리미 인증키가 설정되지 않았습니다. {KEY_HINT}")
        params = {
            "apiKey": self._key,
            "apiType": api_type,
            "sidoCode": sido_code,
            "sggCode": sgg_code,
            "schulKndCode": school_kind,
        }
        try:
            response = await self._http.get(OPEN_API_URL, params=params)
        except httpx.HTTPError as e:
            text = str(e) or type(e).__name__
            raise ApiError(f"[학교알리미] 요청 실패 — {OPEN_API_URL}: {text.replace(self._key, '***')}") from None
        if response.status_code >= 400:
            raise ApiError(f"[학교알리미] HTTP {response.status_code} — {OPEN_API_URL}")
        try:
            body = response.json()
        except ValueError:
            raise ApiError(f"[학교알리미] JSON이 아닌 응답입니다 — {OPEN_API_URL}") from None
        return parse_response(body)
