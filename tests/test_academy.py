import pytest

from ne_edu_open_api_mcp.academy import AcademyService, build_predicate, normalize_row, parse_tuition
from ne_edu_open_api_mcp.cache import FileCache
from ne_edu_open_api_mcp.offices import resolve_office

from .helpers import RecordingNeis, neis_client, neis_row


def test_parse_tuition():
    assert parse_tuition("문법 영어:268000, 리딩:192000") == [
        {"과목": "문법 영어", "금액": 268000},
        {"과목": "리딩", "금액": 192000},
    ]
    assert parse_tuition(" ") == [] and parse_tuition(None) == []


def test_normalize_row_cleans_values():
    row = normalize_row(neis_row(1, "3030영어교습소", kind="교습소"))
    assert row["학원명"] == "3030영어교습소" and row["구분"] == "교습소"
    assert row["휴원시작일"] is None  # 공백뿐인 값
    assert row["휴원종료일"] is None  # 99991231은 종료일 미정
    assert row["설립일"] == "2021-12-28" and row["적재일"] == "2023-10-18"
    assert row["상세주소"] == "3층 301호 (개포동)"  # 앞의 ", " 제거
    assert row["교습비"][0] == {"과목": "문법 영어", "금액": 268000}
    assert row["교습비원문"].startswith("문법 영어:268000")


@pytest.mark.parametrize(
    "value, code",
    [("서울", "B10"), ("b10", "B10"), ("서울특별시교육청", "B10"), ("서울시", "B10"), ("경기도", "J10"), ("제주", "T10")],
)
def test_resolve_office(value, code):
    assert resolve_office(value).code == code


def test_resolve_office_unknown_lists_valid():
    with pytest.raises(ValueError, match="가능한 값.*서울\\(B10\\)"):
        resolve_office("화성")
    with pytest.raises(ValueError):
        resolve_office(" ")


def test_predicate():
    assert build_predicate(None, None, None) is None
    p = build_predicate("교습소", "개원", "문법")
    assert p(normalize_row(neis_row(1, "a", kind="교습소")))
    assert not p(normalize_row(neis_row(1, "a", kind="학원")))
    assert not p(normalize_row(neis_row(1, "a", kind="교습소", status="폐원")))


def _service(rows, tmp_path=None, key="k"):
    rec = RecordingNeis(rows)
    cache = FileCache(tmp_path / "c", ttl_ms=10**9) if tmp_path else None
    return rec, AcademyService(neis_client(rec, key), cache)


async def test_collect_pages_until_enough(tmp_path):
    rows = [neis_row(i, f"학원{i}", kind="교습소" if i % 2 else "학원") for i in range(2500)]
    rec, svc = _service(rows)
    done = await svc.collect({"ATPT_OFCDC_SC_CODE": "B10"}, build_predicate("교습소", None, None), want=10)
    assert len(done.rows) == 10 and all(r["구분"] == "교습소" for r in done.rows)
    assert len(rec.requests) == 1  # 첫 1000건에서 이미 충분
    assert not done.exhausted and done.total == 2500


async def test_collect_exhausts_and_reports(tmp_path):
    rows = [neis_row(i, f"학원{i}") for i in range(2500)]
    rec, svc = _service(rows)
    done = await svc.collect({}, build_predicate("교습소", None, None), want=100)
    assert done.rows == [] and done.exhausted and done.scanned == 2500 and len(rec.requests) == 3


async def test_collect_scan_cap_stops_early():
    rows = [neis_row(i, f"학원{i}") for i in range(5000)]
    rec, svc = _service(rows)
    done = await svc.collect({}, build_predicate("교습소", None, None), want=10, scan_cap=2000)
    assert not done.exhausted and done.scanned == 2000


async def test_collect_without_key_reads_first_page_only():
    rows = [neis_row(i, f"학원{i}") for i in range(50)]
    rec, svc = _service(rows, key=None)
    done = await svc.collect({}, None, want=100)
    assert len(done.rows) == 5 and len(rec.requests) == 1


async def test_cache_skips_second_call_and_never_stores_key(tmp_path):
    rec, svc = _service([neis_row(1, "가")], tmp_path)
    await svc.page({"ATPT_OFCDC_SC_CODE": "B10"}, 1, 10)
    await svc.page({"ATPT_OFCDC_SC_CODE": "B10"}, 1, 10)
    assert len(rec.requests) == 1
    stored = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "c").glob("*.json"))
    assert "neis-secret" not in stored and "KEY" not in stored
