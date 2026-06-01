"""Acts router — Document_АктВыполненныхРабот.

Примітка: BAS OData не підтримує $filter по полю Date в цій конфігурації,
тому фільтрація по даті виконується на стороні Python після отримання даних.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.odata_client import ODataClient, ODataError
from api.schemas import Act, ActCreate, ActCreateResponse, ActListResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/acts", tags=["acts"])

ENTITY = "Document_АктВыполненныхРабот"
_FETCH_LIMIT = 200


def _get_client(request: Request) -> ODataClient:
    return request.app.state.odata_client


def _extract(raw: dict) -> list[dict]:
    d = raw.get("d", raw)
    if isinstance(d, dict):
        results = d.get("results") or d.get("value") or []
        return results if isinstance(results, list) else [d]
    return d if isinstance(d, list) else []


def _filter_by_date(items: list[dict], date_from: str | None, date_to: str | None) -> list[dict]:
    if not date_from and not date_to:
        return items
    dt_from = datetime.fromisoformat(date_from) if date_from else None
    dt_to = datetime.fromisoformat(date_to + "T23:59:59") if date_to else None
    result = []
    for item in items:
        raw_date = item.get("Date") or item.get("Дата")
        if not raw_date:
            continue
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", ""))
        except (ValueError, AttributeError):
            continue
        if dt_from and dt < dt_from:
            continue
        if dt_to and dt > dt_to:
            continue
        result.append(item)
    return result


@router.get("", response_model=ActListResponse)
async def list_acts(
    date_from: str | None = Query(default=None, description="Дата від (РРРР-ММ-ДД)"),
    date_to: str | None = Query(default=None, description="Дата до (РРРР-ММ-ДД)"),
    top: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    client: ODataClient = Depends(_get_client),
) -> ActListResponse:
    """Акти виконаних робіт з фільтром по даті."""
    params: dict = {"$top": _FETCH_LIMIT, "$skip": 0, "$format": "json", "$orderby": "Date desc"}

    log.info("acts_list", date_from=date_from, date_to=date_to, top=top)
    try:
        raw = await client.get(ENTITY, params=params)
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    records = [client.clean_record(r) for r in _extract(raw)]
    records = _filter_by_date(records, date_from, date_to)
    records = records[skip: skip + top]

    return ActListResponse(
        count=len(records),
        items=[Act.model_validate(r) for r in records],
    )


@router.post("", response_model=ActCreateResponse, status_code=201)
async def create_act(
    body: ActCreate,
    client: ODataClient = Depends(_get_client),
) -> ActCreateResponse:
    """Створити новий акт виконаних робіт."""
    payload: dict[str, Any] = {
        "Date": body.date.isoformat(),
        "СуммаДокумента": body.amount,
        "СуммаВключаетНДС": body.includes_vat,
        **body.extra,
    }
    if body.basis:
        payload["ОснованиеПечати"] = body.basis

    log.info("act_create", amount=body.amount, date=body.date)
    try:
        raw = await client.post(ENTITY, body=payload)
    except ODataError as exc:
        status = 400 if exc.status_code in (400, 422) else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    records = _extract(raw)
    record = client.clean_record(records[0] if records else raw)
    return ActCreateResponse(item=Act.model_validate(record))
