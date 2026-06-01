"""Universal OData entity router.

Provides two endpoints that cover all 1C/BAS entity sets:
- GET  /entity/{entity_name} — query / filter records
- POST /entity/{entity_name} — create a new record

The LLM discovers available entity names via GET /metadata, then uses
these endpoints to read and write data without any hardcoded entity logic.
"""

from typing import Any

import structlog
from api.odata_client import ODataClient, ODataError
from api.schemas import EntityCreateResponse, EntityListResponse, EntityQueryParams
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/entity", tags=["entity"])


def _get_odata_client(request: Request) -> ODataClient:
    """FastAPI dependency — returns the shared ODataClient from app state."""
    return request.app.state.odata_client


def _normalize_odata_response(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the items list from an OData JSON response.

    1C OData v3 wraps results in ``{"d": {"results": [...]}}`` for collections
    and ``{"d": {...}}`` for single records. This helper normalises both shapes
    into a plain Python list.

    Args:
        raw: Parsed JSON response from OData service.

    Returns:
        List of entity records.
    """
    d = raw.get("d", raw)
    if isinstance(d, dict):
        results = d.get("results", d.get("value"))
        if isinstance(results, list):
            return results
        return [d]
    if isinstance(d, list):
        return d
    return []


def _build_odata_params(q: EntityQueryParams) -> dict[str, Any]:
    """Convert Pydantic query params to OData ``$``-prefixed query string dict.

    Args:
        q: Validated query parameters from the request.

    Returns:
        Dict suitable for passing to ``httpx`` as ``params``.
    """
    params: dict[str, Any] = {
        "$top": q.top,
        "$skip": q.skip,
        "$format": "json",
    }
    if q.filter:
        params["$filter"] = q.filter
    if q.select:
        params["$select"] = q.select
    if q.orderby:
        params["$orderby"] = q.orderby
    if q.expand:
        params["$expand"] = q.expand
    return params


@router.get(
    "/{entity_name}",
    response_model=EntityListResponse,
    summary="Query records from a 1C entity set",
    response_description="Filtered and paginated list of entity records",
)
async def query_entity(
    entity_name: str,
    q: EntityQueryParams = Depends(),
    client: ODataClient = Depends(_get_odata_client),
) -> EntityListResponse:
    """Fetch records from any 1C/BAS OData entity set.

    Use ``GET /metadata`` first to discover available entity names.

    Args:
        entity_name: Exact 1C entity set name, e.g.
            ``Catalog_Контрагенти`` or ``Document_РахунокНаОплатуПокупцю``.
        q: OData query parameters (filter, top, skip, select, orderby, expand).

    Returns:
        ``{"count": N, "items": [...]}``

    Raises:
        404: Entity set not found in 1C.
        502: Unexpected error from 1C OData.
    """
    params = _build_odata_params(q)
    log.info("entity_query", entity=entity_name, params=params)

    try:
        raw = await client.get(entity_name, params=params)
    except ODataError as exc:
        status = 404 if exc.status_code == 404 else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    items = _normalize_odata_response(raw)
    log.info("entity_query_done", entity=entity_name, count=len(items))
    return EntityListResponse(count=len(items), items=items)


@router.post(
    "/{entity_name}",
    response_model=EntityCreateResponse,
    status_code=201,
    summary="Create a new record in a 1C entity set",
    response_description="The created entity record with server-generated fields",
)
async def create_entity(
    entity_name: str,
    body: dict[str, Any],
    client: ODataClient = Depends(_get_odata_client),
) -> EntityCreateResponse:
    """Create a new record in any 1C/BAS OData entity set.

    The required fields depend on the entity type and the 1C configuration.
    Use ``GET /metadata`` to discover entity names, then consult 1C docs or
    the ``$metadata`` XML for field definitions.

    Args:
        entity_name: Exact 1C entity set name.
        body: Entity fields as a JSON object. Unknown fields are ignored by 1C.

    Returns:
        ``{"item": {...}}`` — created record including server-generated ``Ref``.

    Raises:
        400: Validation error returned by 1C (missing required fields, etc.).
        404: Entity set not found in 1C.
        502: Unexpected error from 1C OData.
    """
    log.info("entity_create", entity=entity_name, fields=list(body.keys()))

    try:
        raw = await client.post(entity_name, body=body)
    except ODataError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        if exc.status_code in (400, 422):
            raise HTTPException(status_code=400, detail=exc.message) from exc
        raise HTTPException(status_code=502, detail=exc.message) from exc

    items = _normalize_odata_response(raw)
    item = items[0] if items else raw
    log.info("entity_create_done", entity=entity_name, ref=item.get("Ref"))
    return EntityCreateResponse(item=item)
