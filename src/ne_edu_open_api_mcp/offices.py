"""시도교육청 코드(ATPT_OFCDC_SC_CODE)와 이름 해석."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Office:
    code: str
    name: str
    short: str  # "서울", "경기" 같은 줄임말


OFFICES: tuple[Office, ...] = (
    Office("B10", "서울특별시교육청", "서울"),
    Office("C10", "부산광역시교육청", "부산"),
    Office("D10", "대구광역시교육청", "대구"),
    Office("E10", "인천광역시교육청", "인천"),
    Office("F10", "광주광역시교육청", "광주"),
    Office("G10", "대전광역시교육청", "대전"),
    Office("H10", "울산광역시교육청", "울산"),
    Office("I10", "세종특별자치시교육청", "세종"),
    Office("J10", "경기도교육청", "경기"),
    Office("K10", "강원특별자치도교육청", "강원"),
    Office("M10", "충청북도교육청", "충북"),
    Office("N10", "충청남도교육청", "충남"),
    Office("P10", "전북특별자치도교육청", "전북"),
    Office("Q10", "전라남도교육청", "전남"),
    Office("R10", "경상북도교육청", "경북"),
    Office("S10", "경상남도교육청", "경남"),
    Office("T10", "제주특별자치도교육청", "제주"),
)


def _valid_list() -> str:
    return ", ".join(f"{o.short}({o.code})" for o in OFFICES)


def resolve_office(value: str) -> Office:
    """코드(B10), 줄임말(서울), 전체 이름(서울특별시교육청) 모두 받는다. 못 찾으면 ValueError."""
    text = (value or "").strip()
    if not text:
        raise ValueError(f"시도교육청을 지정하세요. 가능한 값: {_valid_list()}")
    for o in OFFICES:
        if text.upper() == o.code or text in (o.name, o.short):
            return o
    # "서울시", "서울특별시", "경기도" 처럼 줄임말로 시작하는 입력
    matches = [o for o in OFFICES if text.startswith(o.short)]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"알 수 없는 시도교육청: {text!r}. 가능한 값: {_valid_list()}")
