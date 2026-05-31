"""FastAPI router for OData metadata endpoint."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get(
    "",
    summary="List available 1C entity sets",
    response_description="Cached list of OData entity sets from $metadata",
)
async def get_metadata(request: Request) -> dict:
    """Return the cached list of OData entity sets.

    The list is fetched from ``$metadata`` once at application startup
    and stored in ``app.state.metadata``. Subsequent calls return the
    in-memory cache without hitting 1C.

    Returns:
        JSON object with keys:
        - ``count``: total number of entity sets.
        - ``entities``: list of ``{name, entity_type}`` dicts.

    Raises:
        503: If metadata was not loaded at startup (1C unreachable).
    """
    metadata: list[dict] | None = getattr(request.app.state, "metadata", None)

    if metadata is None:
        raise HTTPException(
            status_code=503,
            detail="Metadata not loaded. 1C OData service may be unavailable.",
        )

    return {"count": len(metadata), "entities": metadata}


@router.post(
    "/refresh",
    summary="Force reload of 1C entity set list",
    response_description="Updated entity set list",
)
async def refresh_metadata(request: Request) -> dict:
    """Force re-fetch of OData $metadata from 1C.

    Useful when the 1C schema has changed and the cached list is stale.
    Replaces ``app.state.metadata`` in place.

    Returns:
        Same structure as GET /metadata.

    Raises:
        502: If 1C OData returns an error during refresh.
    """
    from api.odata_client import ODataError

    client = request.app.state.odata_client
    try:
        entities = await client.fetch_metadata()
    except ODataError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    request.app.state.metadata = entities
    return {"count": len(entities), "entities": entities}
