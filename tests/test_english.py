import json

import pytest

from ne_edu_mcp.academy import AcademyService, normalize_row
from ne_edu_mcp.english import (
    EX_ADULT, EX_NON_ENGLISH, EX_OTHER_SUBJECT, EX_REMOTE, LANG, TUTOR, classify, region, tally, with_ratios,
)
from ne_edu_mcp.tools import register_all_tools

from .helpers import RecordingNeis, capture_registrar, neis_client, neis_row


def row(name, order="보통교과", realm="입시.검정 및 보습", kind="학원", addr="서울특별시 강남구 도곡로 1", detail=None):
    r = normalize_row(neis_row(1, name, kind=kind))
    r.update({"교습계열": order, "분야": realm, "도로명주소": addr, "상세주소": detail})
    return r


@pytest.mark.parametrize(
    ("name", "order", "realm", "expected"),
    [
        ("대치정상어학원", "외국어", "국제화", LANG),
        ("청담어학원", None, "국제화", LANG),  # 계열이 비면 분야로
        ("압구정크라센어학원", None, "종합(대)", LANG),  # 종합 + 이름이 어학원
        ("이써밋영어학원", None, "종합(대)", TUTOR),  # 종합 + 이름에 영어만 → 보습
        ("김동하영어학원", "보통교과", "입시.검정 및 보습", TUTOR),
        ("대치청담어학학원", "보통교과", "입시.검정 및 보습", TUTOR),
        ("서로국어학원", "보통교과", "입시.검정 및 보습", None),  # '어학원' 오탐 방지
        ("스코어학원", "보통교과", "입시.검정 및 보습", None),
        ("플레이팩토플러스수학교습소", "보통교과", "입시.검정 및 보습", None),  # '토플' 오탐 방지
        ("강남중국어학원", "외국어", "국제화", EX_NON_ENGLISH),
        ("김범식독일어학원", "국제", "국제화", EX_ADULT),
        ("영어클리닉원격학원", "외국어", "국제화", EX_REMOTE),
        ("세잎수학교습소", "외국어", "국제화", EX_OTHER_SUBJECT),
        ("욘센세외국어학원", "외국어", "국제화", LANG),  # '외국어' 안의 '국어'는 다른 과목이 아님
        ("와이비엠이씨씨&하이엠수학학원", "외국어", "국제화", LANG),
    ],
)
def test_classify(name, order, realm, expected):
    assert classify(row(name, order, realm)).category == expected


def test_classify_flags():
    v = classify(row("YBM상승어학원"))
    assert v.category == TUTOR and v.lang_named_tutor
    assert classify(row("청담어학원", None, "국제화")).order_missing


@pytest.mark.parametrize(
    ("addr", "detail", "expected"),
    [
        ("경기도 수원시 영통구 봉영로 1", None, ("경기", "수원시")),
        ("세종특별자치시 한누리대로 1", None, ("세종", "세종특별자치시")),
        ("전남광주통합특별시 광산구 손재로 1", None, ("광주", "광산구")),
        ("전남광주통합특별시 순천시 연향로 1", None, ("전남", "순천시")),
        ("인천광역시 중구 흰바위로 45", "206호 (운서동)", ("인천", "영종구")),
        ("인천광역시 중구 인항로 34", "401호 (신흥동3가)", ("인천", "제물포구")),
        ("인천광역시 서구 봉오대로 1", None, ("인천", "서해구")),
        ("경상북도 군위군 군위읍 1", None, ("대구", "군위군")),
        ("충청남도 연기군 조치원읍 충현로 77", None, None),
    ],
)
def test_region(addr, detail, expected):
    assert region(row("x", addr=addr, detail=detail)) == expected


def test_ratios():
    r = with_ratios({"학원_어학원": 2, "학원_보습영어": 6, "교습소_외국어": 1, "교습소_보습영어": 1, "전체_학원": 20, "전체_교습소": 5})
    assert r["합계"] == 10 and r["어학원_비중"] == 20.0 and r["학원중_어학원_비중"] == 25.0 and r["어학원계열_비중"] == 30.0


def test_tally_splits_kinds():
    rows = [
        {"구분": "학원", "_시도": "서울", "_시군구": "강남구", "_분류": LANG},
        {"구분": "교습소", "_시도": "서울", "_시군구": "강남구", "_분류": TUTOR},
        {"구분": "학원", "_시도": "서울", "_시군구": "강남구", "_분류": None},
    ]
    sido, sgg = tally(rows)
    c = sgg[("서울", "강남구")]
    assert c["학원_어학원"] == 1 and c["교습소_보습영어"] == 1 and c["전체_학원"] == 2 and c["전체_교습소"] == 1


async def test_count_tool(tmp_path):
    raw = [neis_row(1, "대치정상어학원"), neis_row(2, "김동하영어학원"), neis_row(3, "서로국어학원"), neis_row(4, "OO영어교습소", kind="교습소")]
    raw[0].update(LE_ORD_NM="외국어", REALM_SC_NM="국제화")
    registrar, server = capture_registrar()
    register_all_tools(registrar, AcademyService(neis_client(RecordingNeis(raw))), None)
    out = json.loads(await server.tools["count_english_academies"](office="서울"))
    gangnam = out["시군구별"][0]
    assert (gangnam["학원_어학원"], gangnam["학원_보습영어"], gangnam["교습소_보습영어"]) == (1, 1, 1)
    assert gangnam["어학원_비중"] == pytest.approx(33.3)


async def test_export_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("NEIS_EXPORT_DIR", str(tmp_path))
    raw = [neis_row(1, "대치정상어학원"), neis_row(2, "김동하영어학원")]
    raw[0].update(LE_ORD_NM="외국어", REALM_SC_NM="국제화")
    registrar, server = capture_registrar()
    register_all_tools(registrar, AcademyService(neis_client(RecordingNeis(raw))), None)
    out = json.loads(await server.tools["export_english_academies"](offices=["서울"]))
    assert out["전국"]["합계"] == 2 and out["시군구"] == 1
    assert (tmp_path / "영어학원_현황_서울.xlsx").exists()
