"""영어 학원·교습소 판정과 지역(시도·시군구) 정리.

판정 원칙
- 이름이 아니라 교육청 등록 정보(교습계열)를 먼저 본다. 이름은 등록 정보가 비었을 때와
  영어/비영어를 가를 때만 보조로 쓴다.
- 학원과 교습소는 같은 기준으로 판정하되 집계는 나눈다.
- 지역은 도로명주소의 시도·시군구로 정한다. 일반구가 있는 시는 시 하나로 묶는다.
"""
import re
from dataclasses import dataclass

# 분류 값
LANG = "어학원"            # 교습소는 '외국어 교습소'로 읽는다
TUTOR = "보습 영어"
EX_ADULT = "제외: 성인 어학"
EX_NON_ENGLISH = "제외: 영어 외 외국어"
EX_REMOTE = "제외: 원격학원"
EX_OTHER_SUBJECT = "제외: 다른 과목 이름(등록 오류 추정)"
EX_STALE = "제외: 옛 주소(충남 연기군)"
CATEGORIES = (LANG, TUTOR)

ENGLISH_NAME = re.compile(r"영어|잉글|english|eng\b|토익|(?<!팩)토플|toeic|toefl|ielts", re.I)
NON_ENGLISH_NAME = re.compile(
    r"중국|일본|차이나|china|japan|hsk|jlpt|독일|프랑스|불어|스페인|러시아|베트남|아랍|이탈리아|태국|한국어|한자|니하오", re.I
)
# '어학원'을 그냥 찾으면 국어학원·영어학원·스코어학원이 섞이므로 앞 글자를 가린다
LANG_SCHOOL_NAME = re.compile(r"어학학원|외국어학원|(?<![국영코])어학원")
REMOTE_NAME = re.compile(r"원격|온라인학원")
OTHER_SUBJECT_NAME = re.compile(r"수학|매쓰|math|국어|논술|미술|아트|진학|과학|테스트|경제", re.I)
# 다른 과목 판정 전에 지우는 말 (외국어 안의 '국어', 영수·연수 안의 '수학' 오탐 방지)
_OTHER_SUBJECT_MASK = re.compile(r"실용외국어|외국어|영수|연수|어진학")
_BRAND_ENGLISH = re.compile(r"와이비엠|ybm", re.I)

TUTOR_REALMS = ("입시.검정 및 보습", "종합(대)")


@dataclass(frozen=True)
class Verdict:
    category: str | None  # LANG, TUTOR, 제외 사유, 또는 None(영어 학원 아님)
    order_missing: bool = False  # 교습계열이 비어 분야·이름으로 판정했는가
    lang_named_tutor: bool = False  # 보습으로 등록됐지만 이름이 어학원인가


def classify(row: dict) -> Verdict:
    """normalize_row로 정리된 행 하나를 판정한다."""
    name = row.get("학원명") or ""
    order = row.get("교습계열")
    realm = row.get("분야")
    non_english = bool(NON_ENGLISH_NAME.search(name)) and not ENGLISH_NAME.search(name)
    english_name = bool(ENGLISH_NAME.search(name))
    lang_name = bool(LANG_SCHOOL_NAME.search(name))

    if order == "국제":
        return Verdict(EX_ADULT)
    is_lang = order == "외국어" or (
        order is None and (realm == "국제화" or (realm == "종합(대)" and lang_name))
    )
    is_tutor = order == "보통교과" or (order is None and realm in TUTOR_REALMS)

    if is_lang:
        if non_english:
            return Verdict(EX_NON_ENGLISH, order is None)
        if (
            not english_name
            and not lang_name
            and not _BRAND_ENGLISH.search(name)
            and OTHER_SUBJECT_NAME.search(_OTHER_SUBJECT_MASK.sub("", name))
        ):
            return Verdict(EX_OTHER_SUBJECT, order is None)
        if REMOTE_NAME.search(name):
            return Verdict(EX_REMOTE, order is None)
        return Verdict(LANG, order is None)
    if is_tutor and (english_name or lang_name) and not non_english:
        if REMOTE_NAME.search(name):
            return Verdict(EX_REMOTE, order is None)
        return Verdict(TUTOR, order is None, lang_name)
    return Verdict(None)


# ── 지역 ────────────────────────────────────────────────────────────
SIDO = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "울산": "울산",
    "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "강원": "강원",
    "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}
OFFICE_SIDO = {
    "서울특별시교육청": "서울", "부산광역시교육청": "부산", "대구광역시교육청": "대구", "인천광역시교육청": "인천",
    "광주광역시교육청": "광주", "대전광역시교육청": "대전", "울산광역시교육청": "울산", "세종특별자치시교육청": "세종",
    "경기도교육청": "경기", "강원특별자치도교육청": "강원", "충청북도교육청": "충북", "충청남도교육청": "충남",
    "전북특별자치도교육청": "전북", "전라북도교육청": "전북", "전라남도교육청": "전남", "경상북도교육청": "경북",
    "경상남도교육청": "경남", "제주특별자치도교육청": "제주",
    "전남광주통합특별시교육청(광주)": "광주", "전남광주통합특별시교육청(전남)": "전남",
}
SIDO_ORDER = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
              "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")
GWANGJU_GU = {"동구", "서구", "남구", "북구", "광산구"}
INTEGRATED = "전남광주통합특별시"
# 인천 2026년 개편: 중구(영종) → 영종구, 중구(내륙)·동구 → 제물포구, 서구 → 서해구, 남구 → 미추홀구
YEONGJONG = re.compile(r"영종|운서|운남|운북|중산동|을왕|덕교|무의|남북동|하늘")
_SGG_END = re.compile(r"[시군구]$")


def region(row: dict) -> tuple[str, str] | None:
    """(시도 줄임말, 시군구). 세종시 출범 전 '충남 연기군' 옛 등록은 None."""
    parts = (row.get("도로명주소") or "").split()
    first = parts[0] if parts else ""
    second = parts[1] if len(parts) > 1 else ""
    if first == INTEGRATED:
        sido = "광주" if second in GWANGJU_GU else "전남"
    else:
        sido = SIDO.get(first) or OFFICE_SIDO.get(row.get("시도교육청") or "")
    if not sido:
        return None
    if sido == "세종":
        return sido, "세종특별자치시"
    known = first in SIDO or first == INTEGRATED
    sgg = second if known and _SGG_END.search(second) else (row.get("행정구역") or "")
    if sido == "충남" and sgg == "연기군":
        return None
    if sido == "경북" and sgg == "군위군":
        return "대구", sgg
    if sido == "인천":
        if sgg == "중구":
            text = f"{row.get('상세주소') or ''} {row.get('도로명주소') or ''}"
            sgg = "영종구" if YEONGJONG.search(text) else "제물포구"
        elif sgg == "동구":
            sgg = "제물포구"
        elif sgg == "서구":
            sgg = "서해구"
        elif sgg == "남구":
            sgg = "미추홀구"
    return sido, sgg


# ── 집계 ────────────────────────────────────────────────────────────
COUNT_KEYS = ("학원_어학원", "학원_보습영어", "교습소_외국어", "교습소_보습영어", "전체_학원", "전체_교습소")


def _bucket(kind: str | None, category: str | None) -> str | None:
    if category == LANG:
        return "학원_어학원" if kind == "학원" else "교습소_외국어"
    if category == TUTOR:
        return "학원_보습영어" if kind == "학원" else "교습소_보습영어"
    return None


def _pct(num: int, den: int) -> float | None:
    return round(num / den * 100, 1) if den else None


def with_ratios(c: dict) -> dict:
    """개수 dict에 계와 비중(%)을 붙인다.

    어학원 비중 = 어학원 ÷ (어학원 + 보습 영어학원 + 영어 교습소)
    학원 중 어학원 비중 = 어학원 ÷ (어학원 + 보습 영어학원)
    어학원 계열 비중 = (어학원 + 외국어 교습소) ÷ 합계
    """
    a, b, k1, k2 = c["학원_어학원"], c["학원_보습영어"], c["교습소_외국어"], c["교습소_보습영어"]
    total = a + b + k1 + k2
    return {
        **c,
        "학원_계": a + b,
        "교습소_계": k1 + k2,
        "합계": total,
        "어학원_비중": _pct(a, total),
        "학원중_어학원_비중": _pct(a, a + b),
        "어학원계열_비중": _pct(a + k1, total),
    }


def tally(rows: list[dict]) -> tuple[dict, dict]:
    """판정이 끝난 행(_시도, _시군구, _분류 포함)을 시도별·시군구별로 센다."""
    by_sido: dict[str, dict] = {}
    by_sgg: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row.get("_시도") is None:
            continue
        key = (row["_시도"], row["_시군구"])
        for bucket_map, k in ((by_sido, key[0]), (by_sgg, key)):
            c = bucket_map.setdefault(k, dict.fromkeys(COUNT_KEYS, 0))
            c["전체_학원" if row.get("구분") == "학원" else "전체_교습소"] += 1
            b = _bucket(row.get("구분"), row.get("_분류"))
            if b:
                c[b] += 1
    return by_sido, by_sgg


def sido_rank(sido: str) -> int:
    return SIDO_ORDER.index(sido) if sido in SIDO_ORDER else len(SIDO_ORDER)


CRITERIA: tuple[tuple[str, str], ...] = (
    ("원칙", "이름이 아니라 교육청 등록 정보(교습계열)를 먼저 본다. 이름은 등록 정보가 비었을 때와 영어/비영어를 가를 때만 쓴다."),
    ("어학원 / 외국어 교습소", "교습계열 '외국어'. 계열이 비면 분야 '국제화', 또는 분야 '종합(대)'이고 이름에 어학원·어학학원·외국어학원."),
    ("보습 영어학원 / 보습 영어 교습소", "교습계열 '보통교과'(계열이 비면 분야 '입시.검정 및 보습'·'종합(대)')이고 이름에 영어·잉글리시·English·토익·토플·어학원·어학학원."),
    ("", "이름에 영어가 없는 종합 보습학원(국영수 등)은 잡히지 않는다 → 보습 영어 수는 최소치."),
    ("제외", "성인 어학(교습계열 '국제'), 영어 외 외국어(이름에 중국어·일본어 등만), 원격학원(이름에 '원격'·'온라인학원'), 외국어로 등록됐지만 이름이 다른 과목인 곳."),
    ("어학원 비중", "어학원 ÷ (어학원 + 보습 영어학원 + 영어 교습소). 참고: 학원 중 어학원 비중, 어학원 계열 비중((어학원 + 외국어 교습소) ÷ 합계)."),
    ("지역", "도로명주소의 시도·시군구. 일반구가 있는 시는 시로 묶음. 인천은 2026년 개편 구(영종·제물포·서해·검단), 군위군은 대구, 전남광주통합특별시는 자치구를 광주로 나눔. 충남 연기군 옛 등록은 제외."),
    ("중복", "두 교육청에 같은 학원이 등록된 경우(학원지정번호+학원명) 1건만 센다."),
)
