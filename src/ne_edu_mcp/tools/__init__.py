"""도구 등록 모듈 모음. 각 모듈이 register_*_tools(registrar, ...)를 제공한다."""
from ..academy import AcademyService
from ..school_service import SchoolDisclosureService
from ..tool_filter import ToolRegistrar
from .academy import register_academy_tools
from .english import register_english_tools
from .school import register_school_tools


def register_all_tools(
    registrar: ToolRegistrar,
    academies: AcademyService | None,
    schools: SchoolDisclosureService | None,
) -> None:
    """NEIS 학원·교습소 도구 4개, 영어 학원 판정 도구 2개, 학교알리미 도구 5개를 등록한다.

    서비스가 None이면(테스트용) 등록만 하고, 호출 시점에 서비스가 필요하다.
    """
    register_academy_tools(registrar, academies)
    register_english_tools(registrar, academies)
    register_school_tools(registrar, schools)
