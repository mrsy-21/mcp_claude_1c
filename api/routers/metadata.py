"""FastAPI router for OData metadata endpoints."""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/metadata", tags=["metadata"])


def _get_metadata(request: Request) -> list[dict]:
    """Return cached metadata or raise 503."""
    metadata: list[dict] | None = getattr(request.app.state, "metadata", None)
    if metadata is None:
        raise HTTPException(
            status_code=503,
            detail="Metadata not loaded. 1C OData service may be unavailable.",
        )
    return metadata


@router.get(
    "",
    summary="List all available 1C entity sets",
    response_description="Cached list of OData entity sets from $metadata",
)
async def get_metadata(request: Request) -> dict:
    """Return the full cached list of OData entity sets.

    The list is fetched from ``$metadata`` once at application startup.
    Use ``/metadata/index`` for a compact grouped view, or
    ``/metadata/search`` to find entities by keyword.

    Returns:
        ``{"count": N, "entities": [{name, entity_type}]}``

    Raises:
        503: If metadata was not loaded at startup.
    """
    metadata = _get_metadata(request)
    return {"count": len(metadata), "entities": metadata}


@router.get(
    "/index",
    summary="Compact grouped index of 1C entity sets",
    response_description="Entity names grouped by type prefix",
)
async def get_metadata_index(request: Request) -> dict:
    """Return a compact grouped index of all entity sets.

    Groups entities by their type prefix (``Catalog``, ``Document``,
    ``AccumulationRegister``, etc.) and strips the prefix from each name
    to keep the response concise.

    This endpoint is designed for LLM consumption — the full list of 584
    entities would use ~20k tokens, while this index uses ~500-800 tokens.

    Returns:
        ``{"total": N, "groups": {"Document": ["РахунокНаОплату", ...], ...}}``

    Raises:
        503: If metadata was not loaded at startup.

    Example LLM usage:
        Call this once to understand what data is available, then use
        ``search_metadata`` to find the exact entity name before querying.
    """
    metadata = _get_metadata(request)
    groups: dict[str, list[str]] = defaultdict(list)

    for entity in metadata:
        name: str = entity["name"]
        # Split on first underscore: "Document_РахунокНаОплату" → ("Document", "РахунокНаОплату")
        if "_" in name:
            prefix, suffix = name.split("_", 1)
            # Skip internal _RecordType variants — not useful for LLM
            if not suffix.endswith("_RecordType"):
                groups[prefix].append(suffix)
        else:
            groups["Other"].append(name)

    # Return count + first 5 examples per group so LLM can see naming patterns
    group_summary = {
        k: {"count": len(v), "examples": v[:5]}
        for k, v in sorted(groups.items())
    }
    return {
        "total": len(metadata),
        "hint": (
            "Use search_metadata(q='keyword') to find exact entity names. "
            "Entity names are in Russian (e.g. search 'счет' not 'рахунок', 'контрагент' works). "
            "Full name = prefix + '_' + suffix, e.g. 'Document_СчетНаОплатуПокупцю'."
        ),
        "groups": group_summary,
    }


@router.get(
    "/search",
    summary="Search entity sets by keyword",
    response_description="Matching entity sets (max 10)",
)
async def search_metadata(
    request: Request,
    q: str = Query(..., min_length=2, description="Search keyword, e.g. 'контрагент' or 'рахунок'"),
) -> dict:
    """Search entity sets by case-insensitive substring match.

    Searches both the full entity name and the suffix after the first
    underscore. Returns at most 10 matches.

    This is the preferred way for the LLM to find an exact entity name
    before calling ``query_entity``.

    Args:
        q: Search keyword (minimum 2 characters).

    Returns:
        ``{"count": N, "query": q, "entities": [{name, entity_type}]}``

    Raises:
        503: If metadata was not loaded at startup.

    Example:
        ``GET /metadata/search?q=контрагент`` →
        ``[{"name": "Catalog_Контрагенты", ...}, ...]``
    """
    metadata = _get_metadata(request)
    q_lower = q.lower()

    matches = [
        entity for entity in metadata
        if q_lower in entity["name"].lower()
    ][:10]

    return {"count": len(matches), "query": q, "entities": matches}


@router.post(
    "/refresh",
    summary="Force reload of 1C entity set list",
    response_description="Updated entity set list",
)
async def refresh_metadata(request: Request) -> dict:
    """Force re-fetch of OData $metadata from 1C.

    Useful when the 1C schema has changed and the cached list is stale.

    Returns:
        Same structure as ``GET /metadata``.

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
