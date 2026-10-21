"""NEIS 학원·교습소 도구: 시도교육청 목록, 검색, 지정번호 조회, 엑셀/CSV 내보내기."""
import json
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from ..academy import COLUMNS, SCAN_CAP, AcademyService, Collected, build_predicate, normalize_row
from ..client import ApiError
from ..export import Sheet, export_sheets
from ..offices import OFFICES, resolve_office
from ..tool_filter import ToolRegistrar

Office = Annotated[
    str, Field(description="시도교육청: 줄임말(서울, 경기), 코드(B10), 전체 이름(서울특별시교육청). list_education_offices 참고")
]
Zone = Annotated[str | None, Field(description="행정구역(시군구) 이름. 정확히 일치해야 한다. 예: 강남구")]
Name = Annotated[str | None, Field(description="학원·교습소 이름에 포함된 글자. 예: 영어")]
Realm = Annotated[str | None, Field(description="분야. 정확히 일치해야 한다. 예: 입시.검정 및 보습")]
CourseOrder = Annotated[str | None, Field(description="교습계열. 정확히 일치해야 한다. 예: 보통교과")]
Course = Annotated[str | None, Field(description="교습과정. 정확히 일치해야 한다. 예: 보습")]
Kind = Annotated[Literal["학원", "교습소"] | None, Field(description="학원 또는 교습소만 (서버가 아닌 이 도구가 걸러낸다)")]
Status = Annotated[str | None, Field(description="등록상태. 예: 개원, 휴원, 폐원 (이 도구가 걸러낸다)")]
CourseList = Annotated[str | None, Field(description="교습과정목록에 포함된 글자. 예: 문법 (이 도구가 걸러낸다)")]

NO_KEY_NOTICE = (
    "NEIS_API_KEY가 설정되지 않아 요청당 5건만 조회됩니다. "
    "https://open.neis.go.kr 에서 인증키를 발급받아 설정하면 최대 1000건씩 조회됩니다."
)
# 도구 인자 → NEIS 요청 인자 (서버가 걸러주는 조건)
SERVER_FILTERS = {
    "zone": "ADMST_ZONE_NM",
    "name": "ACA_NM",
    "field": "REALM_SC_NM",
    "course_order": "LE_ORD_NM",
    "course": "LE_CRSE_NM",
}


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _params(office: str, **filters: str | None) -> dict:
    params: dict = {"ATPT_OFCDC_SC_CODE": resolve_office(office).code}
    for arg, key in SERVER_FILTERS.items():
        value = (filters.get(arg) or "").strip()
        if value:
            params[key] = value
    return params


def export_dir() -> Path:
    return Path(os.environ.get("NEIS_EXPORT_DIR", "").strip() or "exports")


def _scan_note(done: Collected) -> str | None:
    if done.exhausted:
        return None
    return (
        f"서버 조건에 맞는 {done.total}건 중 앞의 {done.scanned}건까지만 훑어서 찾은 결과입니다. "
        "행정구역(zone)이나 이름(name) 같은 서버 조건을 더해 범위를 좁히세요."
    )


def register_academy_tools(registrar: ToolRegistrar, service: AcademyService | None) -> None:
    async def list_education_offices() -> str:
        return _dump([{"코드": o.code, "이름": o.name, "줄임말": o.short} for o in OFFICES])

    async def search_academies(
        office: Office,
        zone: Zone = None,
        name: Name = None,
        field: Realm = None,
        course_order: CourseOrder = None,
        course: Course = None,
        kind: Kind = None,
        status: Status = None,
        course_list: CourseList = None,
        page: Annotated[int, Field(ge=1, description="페이지 번호 (기본 1)")] = 1,
        page_size: Annotated[int, Field(ge=1, le=200, description="한 페이지 건수 (기본 50, 최대 200)")] = 50,
    ) -> str:
        params = _params(office, zone=zone, name=name, field=field, course_order=course_order, course=course)
        predicate = build_predicate(kind, status, course_list)
        out: dict = {}
        if predicate is None:
            result = await service.page(params, page, page_size)
            rows = [normalize_row(r) for r in result.rows]
            out.update(total=result.total, page=page, returned=len(rows), items=rows)
        else:
            done = await service.collect(params, predicate, want=page * page_size)
            rows = done.rows[(page - 1) * page_size :]
            out.update(
                total_by_server_filters=done.total,
                scanned=done.scanned,
                matched_so_far=len(done.rows),
                page=page,
                returned=len(rows),
                items=rows,
            )
            note = _scan_note(done)
            if note:
                out["note"] = note
        if not service.client.has_key:
            out["notice"] = NO_KEY_NOTICE
        return _dump(out)

    async def get_academy(
        office: Office,
        academy_no: Annotated[str, Field(description="학원지정번호. search_academies 결과의 학원지정번호")],
    ) -> str:
        params = _params(office)
        params["ACA_ASNUM"] = academy_no.strip()
        result = await service.page(params, 1, 1)
        if not result.rows:
            raise ValueError(f"{resolve_office(office).name}에서 학원지정번호 {academy_no!r}을(를) 찾을 수 없습니다.")
        return _dump(normalize_row(result.rows[0]))

    async def export_academies(
        office: Office,
        zone: Zone = None,
        name: Name = None,
        field: Realm = None,
        course_order: CourseOrder = None,
        course: Course = None,
        kind: Kind = None,
        status: Status = None,
        course_list: CourseList = None,
        max_rows: Annotated[int, Field(ge=1, le=SCAN_CAP * 5, description="최대 내보낼 건수 (기본 20000)")] = 20000,
        file_name: Annotated[str | None, Field(description="저장할 파일 이름(확장자 제외). 기본: 학원교습소_시도")] = None,
    ) -> str:
        if not service.client.has_key:
            raise ApiError(f"내보내기에는 인증키가 필요합니다. {NO_KEY_NOTICE}")
        params = _params(office, zone=zone, name=name, field=field, course_order=course_order, course=course)
        predicate = build_predicate(kind, status, course_list)
        scan_cap = max_rows if predicate is None else max_rows * 2
        done = await service.collect(params, predicate, want=max_rows, scan_cap=scan_cap)
        columns = [c for c in COLUMNS if c != "교습비"]  # 구조화된 교습비 대신 원문 열을 쓴다
        sheet = Sheet("학원교습소", columns, [[row.get(c) for c in columns] for row in done.rows])
        base = file_name or f"학원교습소_{resolve_office(office).short}"
        result = export_sheets([sheet], export_dir(), base)
        out = {**result.to_dict(), "rows": len(done.rows), "total_by_server_filters": done.total}
        if not done.exhausted:
            out["note"] = f"max_rows({max_rows}) 또는 훑기 한도에서 멈췄습니다. 조건을 좁히거나 max_rows를 늘리세요."
        return _dump(out)

    registrar.register(
        "list_education_offices",
        list_education_offices,
        "시도교육청 코드 목록(17곳). NEIS 학원·교습소 조회의 office 값으로 쓰는 코드와 줄임말을 보여준다.",
    )
    registrar.register(
        "search_academies",
        search_academies,
        "NEIS 교육정보 개방 포털의 학원·교습소 정보를 검색한다 (학원명, 구분, 등록상태, 분야·교습과정, 교습비 내역, 정원, 주소, 전화번호). "
        "office는 필수. 행정구역(zone)은 정확히 일치, 이름(name)은 포함 검색이다. "
        "구분(kind), 등록상태(status), 교습과정목록(course_list)은 서버가 거르지 못해 이 도구가 훑어서 걸러내므로, 가능하면 zone/name으로 먼저 좁히는 편이 정확하다. "
        "교습비 항목은 교습비원문을 과목/금액으로 풀어 쓴 것이다. 대량 수집은 export_academies를 쓴다.",
    )
    registrar.register(
        "get_academy",
        get_academy,
        "학원지정번호로 학원·교습소 한 곳의 전체 정보를 조회한다 (NEIS).",
    )
    registrar.register(
        "export_academies",
        export_academies,
        "조건에 맞는 학원·교습소를 모두 모아 엑셀(xlsx)과 CSV 파일로 저장하고 파일 경로를 돌려준다. 인증키(NEIS_API_KEY)가 필요하다. "
        "저장 폴더는 NEIS_EXPORT_DIR 환경변수(기본: 작업 폴더의 exports).",
    )
