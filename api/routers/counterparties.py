"""Counterparties router — Catalog_Контрагенты.

Примітка: BAS OData не підтримує $filter contains() в цій конфігурації,
тому пошук по назві виконується на стороні Python після отримання даних.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.odata_client import ODataClient, ODataError
from api.schemas import Counterparty, CounterpartyListResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/counterparties", tags=["counterparties"])

ENTITY = "Catalog_Контрагенты"
_FETCH_LIMIT = 200


def _get_client(request: Request) -> ODataClient:
    return request.app.state.odata_client


def _extract(raw: dict) -> list[dict]:
    d = raw.get("d", raw)
    if isinstance(d, dict):
        results = d.get("results") or d.get("value") or []
        return results if isinstance(results, list) else [d]
    return d if isinstance(d, list) else []


@router.get("", response_model=CounterpartyListResponse)
async def list_counterparties(
    search: str | None = Query(default=None, description="Пошук по назві (substring, case-insensitive)"),
    top: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    client: ODataClient = Depends(_get_client),
) -> CounterpartyListResponse:
    """Список контрагентів з опціональним пошуком по назві."""
    params: dict = {"$top": _FETCH_LIMIT, "$skip": 0, "$format": "json"}

    log.info("counterparties_list", search=search, top=top)
    try:
        raw = await client.get(ENTITY, params=params)
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    records = [client.clean_record(r) for r in _extract(raw)]

    if search:
        q = search.lower()
        records = [r for r in records if q in (r.get("Description") or "").lower()]

    records = records[skip: skip + top]
    return CounterpartyListResponse(
        count=len(records),
        items=[Counterparty.model_validate(r) for r in records],
    )
