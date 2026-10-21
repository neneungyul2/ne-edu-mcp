"""학교알리미 공시정보 조회: 시군구 x 학교급 단위로 호출하고 합쳐서 필터/필드 선택을 적용한다."""
import asyncio

from .cache import FileCache, cached
from .schoolinfo import (
    META_IDS,
    SCHOOL_CODE_ID,
    SCHOOL_NAME_ID,
    Item,
    SchoolInfoClient,
    Sgg,
    Sido,
)

CONCURRENCY = 4


def resolve_fields(item: Item, requested: list[str] | None) -> list[str]:
    """출력할 필드 ID 목록. 항목명, 필드 ID, 결과 이름 어느 것으로든 지정할 수 있다.
    지정하지 않으면 시도/지역 메타를 뺀 전체. 학교명과 학교코드는 항상 앞에 둔다."""
    ids = [f.id for f in item.fields]
    if not requested:
        chosen = [i for i in ids if i not in META_IDS]
    else:
        keys = item.keys()
        by_name: dict[str, str] = {}
        for f in item.fields:
            by_name.setdefault(f.label, f.id)
            by_name[keys[f.id]] = f.id
            by_name[f.id.upper()] = f.id
        chosen, unknown = [], []
        for name in requested:
            fid = by_name.get(name.strip()) or by_name.get(name.strip().upper())
            if fid is None:
                unknown.append(name)
            elif fid not in chosen:
                chosen.append(fid)
        if unknown:
            raise ValueError(
                f"{item.name}에 없는 필드: {', '.join(unknown)}. "
                "describe_school_disclosure_item으로 필드 목록을 확인하세요."
            )
    front = [i for i in (SCHOOL_NAME_ID, SCHOOL_CODE_ID) if i in ids]
    return front + [i for i in chosen if i not in front]


def shape_rows(item: Item, rows: list[dict], field_ids: list[str]) -> list[dict]:
    keys = item.keys()
    return [{keys[fid]: row.get(fid) for fid in field_ids} for row in rows]


class SchoolDisclosureService:
    def __init__(self, client: SchoolInfoClient, cache: FileCache | None = None) -> None:
        self.client = client
        self.cache = cache

    async def _one(self, item: Item, sido: Sido, sgg: Sgg, kind: str) -> list[dict]:
        params = {"apiType": item.api_type, "sidoCode": sido.code, "sggCode": sgg.code, "schulKndCode": kind}

        async def fetch() -> list[dict]:
            return await self.client.disclosure(item.api_type, sido.code, sgg.code, kind)

        return await cached(self.cache, "schoolinfo/openApi", params, fetch)

    async def fetch(
        self,
        item: Item,
        sido: Sido,
        sggs: list[Sgg],
        kinds: list[str],
        *,
        school_name: str | None = None,
    ) -> list[dict]:
        """시군구들 x 학교급들을 호출해 원본 행을 합친다. school_name이 있으면 학교명에 포함된 행만."""
        gate = asyncio.Semaphore(CONCURRENCY)

        async def run(sgg: Sgg, kind: str) -> list[dict]:
            async with gate:
                return await self._one(item, sido, sgg, kind)

        batches = await asyncio.gather(*(run(g, k) for g in sggs for k in kinds))
        rows = [row for batch in batches for row in batch]
        if school_name:
            needle = school_name.strip()
            rows = [r for r in rows if needle in str(r.get(SCHOOL_NAME_ID) or "")]
        return rows
