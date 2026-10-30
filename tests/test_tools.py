import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ne_edu_mcp.academy import AcademyService
from ne_edu_mcp.config import load_dotenv_if_present, resolve_api_key, resolve_schoolinfo_key
from ne_edu_mcp.school_service import SchoolDisclosureService
from ne_edu_mcp.tool_filter import parse_tool_allow_list
from ne_edu_mcp.tools import register_all_tools

from .helpers import RecordingNeis, capture_registrar, neis_client, neis_row, school_client

ALL = {
    "list_education_offices", "search_academies", "get_academy", "export_academies",
    "count_english_academies", "export_english_academies",
    "list_school_disclosure_items", "describe_school_disclosure_item", "list_school_regions",
    "get_school_disclosure", "export_school_disclosure",
}


def build(neis_rows=None, key="k", school_rows=None, allow=None):
    rec = RecordingNeis(neis_rows or [])

    def school(request):
        return httpx.Response(200, json={"resultCode": "success", "resultMsg": "성공", "list": school_rows or []})

    registrar, server = capture_registrar(allow)
    register_all_tools(
        registrar,
        AcademyService(neis_client(rec, key)),
        SchoolDisclosureService(school_client(school)),
    )
    return server.tools, rec


def test_registers_all_tools_with_korean_descriptions():
    registrar, server = capture_registrar()
    register_all_tools(registrar, None, None)
    assert set(server.tools) == ALL
    assert all(server.descriptions[n] for n in ALL)


def test_allow_list_limits_tools():
    registrar, server = capture_registrar({"search_academies"})
    register_all_tools(registrar, None, None)
    assert set(server.tools) == {"search_academies"}


def test_parse_allow_list():
    assert parse_tool_allow_list(" a, b ,,") == {"a", "b"}
    assert parse_tool_allow_list("") is None


async def test_search_academies_returns_normalized_page():
    tools, rec = build([neis_row(i, f"영어{i}") for i in range(3)])
    out = json.loads(await tools["search_academies"](office="서울", zone="강남구", name="영어", page_size=2))
    q = rec.requests[0].url.params
    assert q["ATPT_OFCDC_SC_CODE"] == "B10" and q["ADMST_ZONE_NM"] == "강남구" and q["ACA_NM"] == "영어"
    assert out["total"] == 3 and out["returned"] == 2 and out["items"][0]["학원명"] == "영어0"
    assert "notice" not in out


async def test_search_academies_without_key_adds_notice():
    tools, _ = build([neis_row(1, "가")], key=None)
    out = json.loads(await tools["search_academies"](office="서울"))
    assert "5건" in out["notice"]


async def test_search_academies_client_side_filters():
    rows = [neis_row(i, f"학원{i}", kind="교습소" if i == 3 else "학원") for i in range(6)]
    tools, _ = build(rows)
    out = json.loads(await tools["search_academies"](office="서울", kind="교습소"))
    assert [r["학원명"] for r in out["items"]] == ["학원3"]
    assert out["scanned"] == 6 and "note" not in out


async def test_get_academy_found_and_missing():
    tools, rec = build([neis_row(7, "일곱")])
    out = json.loads(await tools["get_academy"](office="서울", academy_no="3000000007"))
    assert out["학원명"] == "일곱" and rec.requests[0].url.params["ACA_ASNUM"] == "3000000007"
    empty_tools, _ = build([])
    with pytest.raises(ToolError, match="찾을 수 없습니다"):  # 등록된 도구는 오류를 ToolError로 감싼다
        await empty_tools["get_academy"](office="서울", academy_no="1")


async def test_export_academies_writes_xlsx_and_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("NEIS_EXPORT_DIR", str(tmp_path))
    tools, _ = build([neis_row(i, f"학원{i}") for i in range(3)])
    out = json.loads(await tools["export_academies"](office="서울", file_name="테스트"))
    assert out["rows"] == 3 and (tmp_path / "테스트.xlsx").exists()
    csv_text = (tmp_path / "테스트-학원교습소.csv").read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[0].startswith("학원명,구분") and "학원2" in csv_text


async def test_export_academies_requires_key():
    tools, _ = build([neis_row(1, "가")], key=None)
    with pytest.raises(ToolError, match="인증키가 필요"):
        await tools["export_academies"](office="서울")


async def test_school_catalog_tools_work_without_calls():
    tools, _ = build()
    listed = json.loads(await tools["list_school_disclosure_items"](query="학생수"))
    assert {i["apiType"] for i in listed} >= {"63", "09"}
    detail = json.loads(await tools["describe_school_disclosure_item"](item="0"))
    assert detail["항목"] == "학교기본정보" and any(f["id"] == "SCHUL_NM" for f in detail["필드"])
    sidos = json.loads(await tools["list_school_regions"]())
    assert len(sidos["시도"]) == 16 and len(sidos["학교급"]) == 6
    sgg = json.loads(await tools["list_school_regions"](sido="세종"))
    assert sgg["시군구"][0]["코드"] == "36110"


async def test_get_school_disclosure_selects_fields_and_limits():
    rows = [{"SCHUL_NM": f"학교{i}", "SCHUL_CODE": f"S{i}", "USER_TELNO": "02", "HMPG_ADRES": "x"} for i in range(30)]
    tools, _ = build(school_rows=rows)
    out = json.loads(await tools["get_school_disclosure"](
        item="학교기본정보", sido="세종", school_kind="초등", fields=["전화번호"], limit=5))
    assert out["전체_건수"] == 30 and out["반환_건수"] == 5 and "note" in out
    assert out["items"][0] == {"학교명": "학교0", "정보공시 학교코드": "S0", "전화번호": "02"}


async def test_export_school_disclosure(tmp_path, monkeypatch):
    monkeypatch.setenv("NEIS_EXPORT_DIR", str(tmp_path))
    tools, _ = build(school_rows=[{"SCHUL_NM": "가", "SCHUL_CODE": "S"}])
    out = json.loads(await tools["export_school_disclosure"](
        item="0", sido="세종", school_kinds=["초등", "중학교"], fields=["학교명"], file_name="학교"))
    assert out["rows"] == 2 and (tmp_path / "학교.xlsx").exists()


def test_config_key_resolution_and_dotenv(tmp_path):
    assert resolve_api_key({"NEIS_API_KEY": " k "}) == "k" and resolve_api_key({}) is None
    assert resolve_schoolinfo_key({"SCHOOLINFO_API_KEY": "s"}) == "s"
    env_file = tmp_path / ".env"
    env_file.write_text('NEIS_API_KEY="from-file"\nSCHOOLINFO_API_KEY=other\n', encoding="utf-8")
    env = {"SCHOOLINFO_API_KEY": "already"}
    load_dotenv_if_present(env_file, env)
    assert env == {"SCHOOLINFO_API_KEY": "already", "NEIS_API_KEY": "from-file"}  # 이미 있는 값은 덮어쓰지 않는다
