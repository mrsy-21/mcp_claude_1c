"""Invoices router — рахунки на оплату покупцям і від постачальників.

Примітка: BAS OData не підтримує $filter по полю Date в цій конфігурації,
тому фільтрація по даті виконується на стороні Python після отримання даних.
"""

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.odata_client import ODataClient, ODataError
from api.schemas import Invoice, InvoiceListResponse, SupplierInvoice, SupplierInvoiceListResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/invoices", tags=["invoices"])

ENTITY_BUYER = "Document_СчетНаОплату"
ENTITY_SUPPLIER = "Document_СчетНаОплатуПоставщика"

# How many records to fetch from OData before Python-side date filtering
_FETCH_LIMIT = 200


def _get_client(request: Request) -> ODataClient:
    return request.app.state.odata_client


def _extract(raw: dict) -> list[dict]:
    d = raw.get("d", raw)
    if isinstance(d, dict):
        results = d.get("results") or d.get("value") or []
        return results if isinstance(results, list) else [d]
    return d if isinstance(d, list) else []


def _filter_by_date(
    items: list[dict],
    date_from: str | None,
    date_to: str | None,
) -> list[dict]:
    """Filter records by Date field on Python side."""
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


@router.get("/outgoing", response_model=InvoiceListResponse)
async def list_invoices_outgoing(
    date_from: str | None = Query(default=None, description="Дата від (РРРР-ММ-ДД)"),
    date_to: str | None = Query(default=None, description="Дата до (РРРР-ММ-ДД)"),
    top: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    client: ODataClient = Depends(_get_client),
) -> InvoiceListResponse:
    """Рахунки на оплату покупцям (Document_СчетНаОплату)."""
    params: dict = {"$top": _FETCH_LIMIT, "$skip": 0, "$format": "json", "$orderby": "Date desc"}

    log.info("invoices_outgoing", date_from=date_from, date_to=date_to, top=top)
    try:
        raw = await client.get(ENTITY_BUYER, params=params)
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    records = [client.clean_record(r) for r in _extract(raw)]
    records = _filter_by_date(records, date_from, date_to)
    records = records[skip: skip + top]

    return InvoiceListResponse(
        count=len(records),
        items=[Invoice.model_validate(r) for r in records],
    )


@router.get("/incoming", response_model=SupplierInvoiceListResponse)
async def list_invoices_incoming(
    date_from: str | None = Query(default=None, description="Дата від (РРРР-ММ-ДД)"),
    date_to: str | None = Query(default=None, description="Дата до (РРРР-ММ-ДД)"),
    top: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    client: ODataClient = Depends(_get_client),
) -> SupplierInvoiceListResponse:
    """Рахунки на оплату від постачальників (Document_СчетНаОплатуПоставщика)."""
    params: dict = {"$top": _FETCH_LIMIT, "$skip": 0, "$format": "json", "$orderby": "Date desc"}

    log.info("invoices_incoming", date_from=date_from, date_to=date_to, top=top)
    try:
        raw = await client.get(ENTITY_SUPPLIER, params=params)
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    records = [client.clean_record(r) for r in _extract(raw)]
    records = _filter_by_date(records, date_from, date_to)
    records = records[skip: skip + top]

    return SupplierInvoiceListResponse(
        count=len(records),
        items=[SupplierInvoice.model_validate(r) for r in records],
    )
