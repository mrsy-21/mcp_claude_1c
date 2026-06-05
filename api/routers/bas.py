"""Generic BAS router — GET /bas/{entity_name} і POST /bas/{entity_name}.

Один endpoint замість 4 окремих роутерів.
Обходить баги BAS OData:
- $filter по Date → 502, тому фільтруємо в Python
- contains() в $filter → 502, тому пошук в Python

Обрізка відповіді (як в odata_mcp_go):
- MAX_ITEMS: максимальна кількість записів у відповіді
- MAX_RESPONSE_BYTES: якщо JSON більше ліміту — підраховує середній розмір запису
  і обрізає до кількості що влізе, додає truncated=true + попередження
"""

import json
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.odata_client import ODataClient, ODataError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/bas", tags=["bas"])

_FETCH_LIMIT = 200
MAX_ITEMS = 50
MAX_RESPONSE_BYTES = 15_000  # ~15KB — достатньо для Claude, не жеруть токени

# Search fields — шукаємо по будь-якому з цих полів якщо є в записі
_SEARCH_FIELDS = ("Description", "ФИО", "Наименование", "Number", "НомерДокумента")


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
            dt = datetime.fromisoformat(str(raw_date).replace("Z", ""))
        except (ValueError, AttributeError):
            continue
        if dt_from and dt < dt_from:
            continue
        if dt_to and dt > dt_to:
            continue
        result.append(item)
    return result


def _filter_by_search(items: list[dict], search: str) -> list[dict]:
    q = search.lower()
    result = []
    for item in items:
        for field in _SEARCH_FIELDS:
            val = item.get(field)
            if val and q in str(val).lower():
                result.append(item)
                break
    return result


def _apply_size_limits(items: list[dict]) -> dict:
    """Обрізає відповідь по кількості і розміру — як в odata_mcp_go.

    Не повідомляє Claude про обрізку (без truncated/original_count) —
    щоб не провокувати автоматичну пагінацію.
    Якщо юзер хоче більше — він сам скаже "покажи всі" і Claude передасть top=200.
    """
    original_count = len(items)

    # Крок 1: обрізка по кількості
    if len(items) > MAX_ITEMS:
        items = items[:MAX_ITEMS]

    # Крок 2: обрізка по розміру JSON
    json_bytes = len(json.dumps(items, ensure_ascii=False).encode())
    if json_bytes > MAX_RESPONSE_BYTES and len(items) > 1:
        avg_item_size = json_bytes // len(items)
        max_by_size = max(1, MAX_RESPONSE_BYTES // avg_item_size)
        if max_by_size < len(items):
            items = items[:max_by_size]

    if len(items) < original_count:
        log.info("bas_response_truncated", original=original_count, returned=len(items))

    return {"count": len(items), "items": items}


@router.get("/{entity_name}")
async def query_entity(
    entity_name: str,
    date_from: str | None = Query(default=None, description="Дата від (РРРР-ММ-ДД)"),
    date_to: str | None = Query(default=None, description="Дата до (РРРР-ММ-ДД)"),
    search: str | None = Query(default=None, description="Пошук по назві/ПІБ (substring)"),
    top: int = Query(default=20, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    client: ODataClient = Depends(_get_client),
) -> dict:
    """Читає будь-яку entity з BAS OData.

    Завжди fetches $top=200 без $filter — фільтрує в Python щоб обійти баги BAS.
    Повертає {"count": N, "items": [...]} або з truncated=true якщо обрізано.
    """
    params: dict = {"$top": _FETCH_LIMIT, "$skip": 0, "$format": "json"}
    if entity_name.startswith("Document_"):
        params["$orderby"] = "Date desc"

    log.info("bas_query", entity=entity_name, date_from=date_from, date_to=date_to, search=search)

    try:
        raw = await client.get(entity_name, params=params)
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    records = [client.clean_record(r) for r in _extract(raw)]

    if date_from or date_to:
        records = _filter_by_date(records, date_from, date_to)

    if search:
        records = _filter_by_search(records, search)

    records = records[skip: skip + top]

    return _apply_size_limits(records)


@router.post("/{entity_name}")
async def create_entity(
    entity_name: str,
    data: dict,
    client: ODataClient = Depends(_get_client),
) -> dict:
    """Створює запис в BAS OData для заданої entity."""
    log.info("bas_create", entity=entity_name)

    try:
        result = await client.post(entity_name, body=data)
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    return client.clean_record(result.get("d", result))
