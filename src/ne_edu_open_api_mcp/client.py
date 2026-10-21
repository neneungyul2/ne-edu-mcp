"""NEIS 교육정보 개방 포털 HTTP 클라이언트 (httpx 비동기)."""
from dataclasses import dataclass, field
from typing import Any

import httpx

BASE_URL = "https://open.neis.go.kr/hub"
ACADEMY_SERVICE = "acaInsTiInfo"
MAX_PAGE_SIZE = 1000  # 인증키가 있을 때 요청당 최대 건수
KEYLESS_PAGE_SIZE = 5  # 인증키가 없으면 pSize와 관계없이 5건만 나온다

OK_CODE = "INFO-000"
NO_DATA_CODE = "INFO-200"


class ApiError(Exception):
    """NEIS 호출 실패. 메시지에는 인증키 값이 들어가지 않는다."""


@dataclass
class Page:
    total: int
    rows: list[dict] = field(default_factory=list)


def _result(body: dict) -> dict | None:
    """응답의 RESULT(코드, 메시지). 정상 응답은 head 안에, 오류 응답은 최상위에 있다."""
    if isinstance(body.get("RESULT"), dict):
        return body["RESULT"]
    for section in body.get(ACADEMY_SERVICE, []):
        for item in section.get("head", []):
            if isinstance(item, dict) and isinstance(item.get("RESULT"), dict):
                return item["RESULT"]
    return None


def parse_academy_page(body: dict) -> Page:
    """NEIS JSON 응답을 Page로. 데이터 없음(INFO-200)은 빈 Page, 그 밖의 오류는 ApiError."""
    result = _result(body)
    if result is None:
        raise ApiError(f"[NEIS] 예상하지 못한 응답 형식입니다: {str(body)[:200]}")
    code, message = result.get("CODE", ""), result.get("MESSAGE", "")
    if code == NO_DATA_CODE:
        return Page(0, [])
    if code != OK_CODE:
        hint = ""
        if code == "ERROR-290":
            hint = " NEIS_API_KEY가 올바른지 확인하세요 (https://open.neis.go.kr 에서 신청)."
        raise ApiError(f"[NEIS] {code}: {message}{hint}")
    total, rows = 0, []
    for section in body.get(ACADEMY_SERVICE, []):
        for item in section.get("head", []):
            if isinstance(item, dict) and "list_total_count" in item:
                total = int(item["list_total_count"])
        if "row" in section:
            rows = section["row"]
    return Page(total, rows)


class NeisClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(transport=transport, timeout=timeout)

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    @property
    def max_page_size(self) -> int:
        return MAX_PAGE_SIZE if self._key else KEYLESS_PAGE_SIZE

    async def aclose(self) -> None:
        await self._http.aclose()

    async def academy_info(self, params: dict[str, Any], *, page: int = 1, page_size: int = 100) -> Page:
        """학원교습소정보(acaInsTiInfo) 한 페이지. None 값 파라미터는 보내지 않는다."""
        query: dict[str, Any] = {k: v for k, v in params.items() if v is not None}
        query.update(Type="json", pIndex=page, pSize=min(page_size, self.max_page_size))
        if self._key:
            query["KEY"] = self._key
        url = f"{BASE_URL}/{ACADEMY_SERVICE}"
        try:
            response = await self._http.get(url, params=query)
        except httpx.HTTPError as e:
            raise ApiError(f"[NEIS] 요청 실패 — {url}: {self._redact(str(e) or type(e).__name__)}") from None
        if response.status_code >= 400:
            raise ApiError(f"[NEIS] HTTP {response.status_code} — {url}")
        try:
            body = response.json()
        except ValueError:
            raise ApiError(f"[NEIS] JSON이 아닌 응답입니다 — {url}") from None
        return parse_academy_page(body)

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "***") if self._key else text
