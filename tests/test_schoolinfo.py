import httpx
import pytest

from ne_neis_open_api_mcp.client import ApiError
from ne_neis_open_api_mcp.school_service import SchoolDisclosureService, resolve_fields, shape_rows
from ne_neis_open_api_mcp.schoolinfo import (
    find_item,
    items,
    parse_response,
    regions,
    resolve_school_kind,
    resolve_sggs,
    resolve_sido,
)

from .helpers import school_client


def test_catalog_matches_official_files():
    assert len(items()) == 35 and len({i.api_type for i in items()}) == 35
    assert [s.code for s in regions()][:2] == ["11", "12"]
    base = find_item("0")
    assert base.name == "학교기본정보"
    assert {f.id for f in base.fields} >= {"SCHUL_NM", "SCHUL_CODE", "SCHUL_RDNMA"}


@pytest.mark.parametrize(
    "query, api_type",
    [("62", "62"), (62, "62"), ("8", "08"), ("08", "08"), ("0", "0"), ("학교 현황", "62"), ("성별", "63"), ("교복", "73")],
)
def test_find_item(query, api_type):
    assert find_item(query).api_type == api_type


def test_find_item_ambiguous_and_unknown():
    with pytest.raises(ValueError, match="여러 개"):
        find_item("현황")
    with pytest.raises(ValueError, match="알 수 없는"):
        find_item("없는항목")


@pytest.mark.parametrize(
    "text, code",
    [("서울", "11"), ("서울특별시", "11"), ("11", "11"), ("경기", "41"), ("광주", "12"), ("전남", "12"), ("제주특별자치도", "50")],
)
def test_resolve_sido(text, code):
    assert resolve_sido(text).code == code


def test_resolve_sido_unknown():
    with pytest.raises(ValueError, match="가능한 값"):
        resolve_sido("달나라")


def test_resolve_sgg():
    seoul = resolve_sido("서울")
    assert len(resolve_sggs(seoul, None)) == 25
    assert [g.code for g in resolve_sggs(seoul, "종로구")] == ["11110"]
    suwon = resolve_sggs(resolve_sido("경기"), "수원시")
    assert len(suwon) >= 3 and all(g.name.startswith("수원시") for g in suwon)
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        resolve_sggs(seoul, "없는구")


@pytest.mark.parametrize("text, code", [("초등", "02"), ("초등학교", "02"), ("중", "03"), ("고등학교", "04"), ("04", "04"), ("각종", "07")])
def test_resolve_school_kind(text, code):
    assert resolve_school_kind(text) == code


def test_resolve_school_kind_unknown():
    with pytest.raises(ValueError, match="가능한 값"):
        resolve_school_kind("대학")


def test_parse_response():
    assert parse_response({"resultCode": "success", "resultMsg": "성공", "list": [{"a": 1}]}) == [{"a": 1}]
    assert parse_response({"resultCode": "success", "resultMsg": "성공"}) == []
    with pytest.raises(ApiError, match="유효하지 않은 apiKey.*SCHOOLINFO_API_KEY"):
        parse_response({"resultCode": "fail", "resultMsg": "유효하지 않은 apiKey입니다."})
    with pytest.raises(ApiError, match="예상하지 못한"):
        parse_response("<html>")


def test_item_keys_are_unique_even_with_repeated_labels():
    for it in items():
        keys = list(it.keys().values())
        assert len(keys) == len(set(keys)), it.name


def test_resolve_fields_default_and_selection():
    it = find_item("0")
    default = resolve_fields(it, None)
    assert default[:2] == ["SCHUL_NM", "SCHUL_CODE"] and "ATPT_OFCDC_ORG_NM" not in default
    chosen = resolve_fields(it, ["전화번호", "HMPG_ADRES", "학교명"])
    assert chosen == ["SCHUL_NM", "SCHUL_CODE", "USER_TELNO", "HMPG_ADRES"]
    with pytest.raises(ValueError, match="없는 필드: 없음"):
        resolve_fields(it, ["없음"])


def test_shape_rows_renames_to_labels():
    it = find_item("0")
    out = shape_rows(it, [{"SCHUL_NM": "한국초", "SCHUL_CODE": "S1", "USER_TELNO": "02"}], ["SCHUL_NM", "USER_TELNO"])
    assert out == [{"학교명": "한국초", "전화번호": "02"}]


class Recorder:
    def __init__(self, by_sgg):
        self.by_sgg = by_sgg
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        rows = self.by_sgg.get(request.url.params["sggCode"], [])
        return httpx.Response(200, json={"resultCode": "success", "resultMsg": "성공", "list": rows})


async def test_client_sends_documented_params():
    rec = Recorder({"11110": [{"SCHUL_NM": "가"}]})
    rows = await school_client(rec).disclosure("0", "11", "11110", "02")
    q = rec.requests[0].url.params
    assert rec.requests[0].url.path == "/openApi.do"
    assert dict(q) == {"apiKey": "school-secret", "apiType": "0", "sidoCode": "11", "sggCode": "11110", "schulKndCode": "02"}
    assert rows == [{"SCHUL_NM": "가"}]


async def test_client_without_key_explains():
    with pytest.raises(ApiError, match="SCHOOLINFO_API_KEY"):
        await school_client(Recorder({}), key=None).disclosure("0", "11", "11110", "02")


async def test_client_errors_never_contain_key():
    def boom(request):
        raise httpx.ConnectError("apiKey=school-secret refused")

    with pytest.raises(ApiError) as e:
        await school_client(boom).disclosure("0", "11", "11110", "02")
    assert "school-secret" not in str(e.value)


async def test_service_fans_out_over_sgg_and_kinds_and_filters_name():
    rec = Recorder({"11110": [{"SCHUL_NM": "한국초등학교"}], "11140": [{"SCHUL_NM": "서울초등학교"}]})
    svc = SchoolDisclosureService(school_client(rec), None)
    seoul = resolve_sido("서울")
    rows = await svc.fetch(find_item("0"), seoul, resolve_sggs(seoul, None), ["02", "03"])
    assert len(rec.requests) == 25 * 2  # 시군구 25 x 학교급 2
    assert len(rows) == 4  # 두 시군구의 학교가 학교급마다 한 번씩
    named = await svc.fetch(find_item("0"), seoul, resolve_sggs(seoul, "종로구"), ["02"], school_name="한국")
    assert [r["SCHUL_NM"] for r in named] == ["한국초등학교"]
