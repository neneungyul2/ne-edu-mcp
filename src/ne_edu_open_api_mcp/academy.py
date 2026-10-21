"""NEIS 학원교습소정보: 응답 행 정리와 조회 서비스."""
import re
from collections.abc import Callable
from dataclasses import dataclass

from .cache import FileCache, cached
from .client import NeisClient, Page

SCAN_CAP = 10_000  # 클라이언트 쪽 필터를 쓸 때 한 번에 훑어보는 최대 건수

# NEIS 필드 → 읽기 쉬운 이름 (출력 순서)
FIELDS: tuple[tuple[str, str], ...] = (
    ("ACA_NM", "학원명"),
    ("ACA_INSTI_SC_NM", "구분"),
    ("ATPT_OFCDC_SC_NM", "시도교육청"),
    ("ADMST_ZONE_NM", "행정구역"),
    ("ACA_ASNUM", "학원지정번호"),
    ("REG_STTUS_NM", "등록상태"),
    ("ESTBL_YMD", "설립일"),
    ("REG_YMD", "등록일"),
    ("CAA_BEGIN_YMD", "휴원시작일"),
    ("CAA_END_YMD", "휴원종료일"),
    ("TOFOR_SMTOT", "정원합계"),
    ("DTM_RCPTN_ABLTY_NMPR_SMTOT", "일시수용능력인원"),
    ("REALM_SC_NM", "분야"),
    ("LE_ORD_NM", "교습계열"),
    ("LE_CRSE_LIST_NM", "교습과정목록"),
    ("LE_CRSE_NM", "교습과정"),
    ("PSNBY_THCC_CNTNT", "교습비원문"),
    ("THCC_OTHBC_YN", "교습비공개여부"),
    ("BRHS_ACA_YN", "기숙학원여부"),
    ("FA_RDNZC", "우편번호"),
    ("FA_RDNMA", "도로명주소"),
    ("FA_RDNDA", "상세주소"),
    ("FA_TELNO", "전화번호"),
    ("LOAD_DTM", "적재일"),
)
COLUMNS: tuple[str, ...] = tuple(label for _, label in FIELDS) + ("교습비",)

_DATE = re.compile(r"\d{8}")
_TUITION = re.compile(r"([^,:]+?)\s*:\s*(\d+)")


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: object) -> str | None:
    text = _text(value)
    if text and _DATE.fullmatch(text):
        if text == "99991231":
            return None  # 종료일이 정해지지 않았다는 뜻의 자리표시 값
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def parse_tuition(raw: str | None) -> list[dict]:
    """'문법 영어:268000, 리딩:268000' → [{'과목': '문법 영어', '금액': 268000}, ...]"""
    if not raw:
        return []
    return [{"과목": name.strip(), "금액": int(amount)} for name, amount in _TUITION.findall(raw)]


def normalize_row(row: dict) -> dict:
    """공백뿐인 값은 None으로, 날짜는 YYYY-MM-DD로, 교습비 원문은 구조화해서 덧붙인다."""
    out: dict = {}
    for source, label in FIELDS:
        value = row.get(source)
        if source.endswith("_YMD") or source == "LOAD_DTM":
            value = _date(value)
        elif isinstance(value, str):
            value = _text(value)
        out[label] = value
    detail = out.get("상세주소")
    if isinstance(detail, str):
        out["상세주소"] = detail.lstrip(", ").strip() or None
    out["교습비"] = parse_tuition(out.get("교습비원문"))
    return out


def build_predicate(
    kind: str | None, status: str | None, course_list: str | None
) -> Callable[[dict], bool] | None:
    """서버가 걸러주지 않는 조건(구분, 등록상태, 교습과정목록)을 정리된 행에 적용한다."""
    if not (kind or status or course_list):
        return None

    def match(row: dict) -> bool:
        if kind and row.get("구분") != kind:
            return False
        if status and row.get("등록상태") != status:
            return False
        return not (course_list and course_list not in (row.get("교습과정목록") or ""))

    return match


@dataclass
class Collected:
    rows: list[dict]
    total: int  # 서버 필터에 맞는 전체 건수 (클라이언트 필터 적용 전)
    scanned: int  # 실제로 훑어본 건수
    exhausted: bool  # 서버 필터에 맞는 건을 끝까지 훑었는가


class AcademyService:
    def __init__(self, client: NeisClient, cache: FileCache | None = None) -> None:
        self.client = client
        self.cache = cache

    async def page(self, params: dict, page: int, page_size: int) -> Page:
        size = min(page_size, self.client.max_page_size)

        async def fetch() -> dict:
            result = await self.client.academy_info(params, page=page, page_size=size)
            return {"total": result.total, "rows": result.rows}

        data = await cached(self.cache, "neis/acaInsTiInfo", {**params, "pIndex": page, "pSize": size}, fetch)
        return Page(data["total"], data["rows"])

    async def collect(
        self,
        params: dict,
        predicate: Callable[[dict], bool] | None,
        *,
        want: int,
        scan_cap: int = SCAN_CAP,
    ) -> Collected:
        """조건에 맞는 행을 want건까지 모은다. 인증키가 없으면 첫 페이지(5건)만 본다."""
        matched: list[dict] = []
        scanned, total, page_no = 0, 0, 1
        size = self.client.max_page_size
        while True:
            result = await self.page(params, page_no, size)
            total = result.total
            scanned += len(result.rows)
            for raw in result.rows:
                row = normalize_row(raw)
                if predicate is None or predicate(row):
                    matched.append(row)
            exhausted = scanned >= total or not result.rows
            if exhausted or len(matched) >= want or scanned >= scan_cap or not self.client.has_key:
                return Collected(matched[:want], total, scanned, exhausted)
            page_no += 1
