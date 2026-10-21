import pytest

from ne_neis_open_api_mcp.client import ApiError, parse_academy_page

from .helpers import NEIS_BAD_KEY, NEIS_NO_DATA, RecordingNeis, neis_client, neis_ok, neis_row


def test_parse_ok():
    page = parse_academy_page(neis_ok([neis_row(1, "가")], total=25))
    assert page.total == 25 and len(page.rows) == 1


def test_parse_no_data_is_empty_page():
    page = parse_academy_page(NEIS_NO_DATA)
    assert page.total == 0 and page.rows == []


def test_parse_error_has_key_hint():
    with pytest.raises(ApiError, match="ERROR-290.*NEIS_API_KEY"):
        parse_academy_page(NEIS_BAD_KEY)


def test_parse_unknown_shape():
    with pytest.raises(ApiError, match="예상하지 못한"):
        parse_academy_page({"foo": 1})


async def test_request_params_and_key():
    rec = RecordingNeis([neis_row(1, "가")])
    page = await neis_client(rec).academy_info({"ATPT_OFCDC_SC_CODE": "B10", "ACA_NM": None}, page=2, page_size=50)
    q = rec.requests[0].url.params
    assert rec.requests[0].url.path == "/hub/acaInsTiInfo"
    assert q["KEY"] == "neis-secret" and q["Type"] == "json"
    assert q["ATPT_OFCDC_SC_CODE"] == "B10" and q["pIndex"] == "2" and q["pSize"] == "50"
    assert "ACA_NM" not in q  # None 값은 보내지 않는다
    assert page.total == 1


async def test_page_size_capped_at_1000_with_key_and_5_without():
    rec = RecordingNeis([neis_row(1, "가")])
    await neis_client(rec).academy_info({}, page_size=5000)
    assert rec.requests[0].url.params["pSize"] == "1000"
    rec2 = RecordingNeis([neis_row(1, "가")])
    client = neis_client(rec2, key=None)
    await client.academy_info({}, page_size=100)
    assert rec2.requests[0].url.params["pSize"] == "5"
    assert "KEY" not in rec2.requests[0].url.params
    assert not client.has_key


async def test_http_error_message_never_contains_key():
    import httpx

    def boom(request):
        raise httpx.ConnectError("failed for KEY=neis-secret")

    with pytest.raises(ApiError) as e:
        await neis_client(boom).academy_info({})
    assert "neis-secret" not in str(e.value)


async def test_http_status_error():
    import httpx

    with pytest.raises(ApiError, match="HTTP 500"):
        await neis_client(lambda r: httpx.Response(500)).academy_info({})
