"""MCP 서버 조립과 실행 진입점."""
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from .academy import AcademyService
from .cache import FileCache, default_cache
from .client import NeisClient
from .config import load_dotenv_if_present, resolve_api_key, resolve_schoolinfo_key
from .school_service import SchoolDisclosureService
from .schoolinfo import SchoolInfoClient
from .tool_filter import ToolRegistrar, parse_tool_allow_list
from .tools import register_all_tools

SERVER_NAME = "ne-neis-open-api-mcp"


def create_server(
    neis: NeisClient | None = None,
    schoolinfo: SchoolInfoClient | None = None,
    *,
    allow: set[str] | None = None,
    cache: FileCache | None = None,
) -> MCPServer:
    """서버를 만들고 도구를 등록한다. 종료할 때 클라이언트를 닫는다."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            for client in (neis, schoolinfo):
                if client is not None:
                    await client.aclose()

    server = MCPServer(SERVER_NAME, lifespan=lifespan)
    registrar = ToolRegistrar(server, allow)
    academies = AcademyService(neis, cache) if neis is not None else None
    schools = SchoolDisclosureService(schoolinfo, cache) if schoolinfo is not None else None
    register_all_tools(registrar, academies, schools)
    registrar.warn_unknown()
    return server


def main() -> None:
    """stdio로 서버를 실행한다. stdout에는 MCP 프로토콜만 나가고 로그와 오류는 stderr로 간다."""
    # Windows 기본 인코딩(cp949 등)에서도 한글 메시지가 깨지지 않게 stderr를 UTF-8로 고정한다
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv_if_present()
    neis_key = resolve_api_key(os.environ)
    school_key = resolve_schoolinfo_key(os.environ)
    if neis_key is None:
        print("[안내] NEIS_API_KEY가 없어 NEIS 조회는 요청당 5건으로 제한됩니다.", file=sys.stderr)
    if school_key is None:
        print("[안내] SCHOOLINFO_API_KEY가 없어 학교알리미 조회 도구는 사용할 수 없습니다 (항목·지역 안내만 가능).", file=sys.stderr)
    allow = parse_tool_allow_list(os.environ.get("NEIS_TOOLS_ALLOW"))
    create_server(NeisClient(neis_key), SchoolInfoClient(school_key), allow=allow, cache=default_cache()).run()


if __name__ == "__main__":
    main()
