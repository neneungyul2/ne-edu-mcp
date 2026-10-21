"""테스트용 가짜 응답과 서버 모음."""
import httpx

from ne_edu_mcp.client import NeisClient
from ne_edu_mcp.schoolinfo import SchoolInfoClient
from ne_edu_mcp.tool_filter import ToolRegistrar


def neis_row(no: int, name: str, kind: str = "학원", status: str = "개원", zone: str = "강남구") -> dict:
    return {
        "ATPT_OFCDC_SC_CODE": "B10", "ATPT_OFCDC_SC_NM": "서울특별시교육청", "ADMST_ZONE_NM": zone,
        "ACA_INSTI_SC_NM": kind, "ACA_ASNUM": str(3000000000 + no), "ACA_NM": name,
        "ESTBL_YMD": "20211228", "REG_YMD": "20211228", "REG_STTUS_NM": status,
        "CAA_BEGIN_YMD": "        ", "CAA_END_YMD": "99991231", "TOFOR_SMTOT": 24,
        "DTM_RCPTN_ABLTY_NMPR_SMTOT": 9, "REALM_SC_NM": "입시.검정 및 보습", "LE_ORD_NM": "보통교과",
        "LE_CRSE_LIST_NM": "문법 영어", "LE_CRSE_NM": "보습",
        "PSNBY_THCC_CNTNT": "문법 영어:268000, 리딩:192000", "THCC_OTHBC_YN": "Y", "BRHS_ACA_YN": "N",
        "FA_RDNMA": "서울특별시 강남구 개포로82길 7", "FA_RDNDA": ", 3층 301호 (개포동)", "FA_RDNZC": "06329",
        "FA_TELNO": "02-0000-0000", "LOAD_DTM": "20231018",
    }


def neis_ok(rows: list[dict], total: int | None = None) -> dict:
    return {
        "acaInsTiInfo": [
            {"head": [{"list_total_count": len(rows) if total is None else total},
                      {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}}]},
            {"row": rows},
        ]
    }


NEIS_NO_DATA = {"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}
NEIS_BAD_KEY = {"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}}


class RecordingNeis:
    """요청을 기록하고, 주어진 전체 행을 pIndex/pSize에 맞춰 잘라 주는 NEIS 대역 transport."""

    def __init__(self, rows: list[dict] | None = None, body: dict | None = None) -> None:
        self.rows = rows or []
        self.body = body
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.body is not None:
            return httpx.Response(200, json=self.body)
        q = request.url.params
        size, index = int(q["pSize"]), int(q["pIndex"])
        chunk = self.rows[(index - 1) * size : index * size]
        return httpx.Response(200, json=neis_ok(chunk, total=len(self.rows)) if self.rows else NEIS_NO_DATA)


def neis_client(handler, key: str | None = "neis-secret") -> NeisClient:
    return NeisClient(key, transport=httpx.MockTransport(handler))


def school_client(handler, key: str | None = "school-secret") -> SchoolInfoClient:
    return SchoolInfoClient(key, transport=httpx.MockTransport(handler))


class CaptureServer:
    """add_tool로 등록된 함수를 모아 직접 호출할 수 있게 한다."""

    def __init__(self) -> None:
        self.tools: dict = {}
        self.descriptions: dict = {}

    def add_tool(self, fn, name=None, description=None, **kwargs):
        self.tools[name] = fn
        self.descriptions[name] = description


def capture_registrar(allow=None) -> tuple[ToolRegistrar, CaptureServer]:
    server = CaptureServer()
    return ToolRegistrar(server, allow), server
