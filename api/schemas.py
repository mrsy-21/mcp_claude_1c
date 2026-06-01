"""Pydantic schemas for FastAPI request/response validation."""

from typing import Any

from pydantic import BaseModel, Field


class EntityQueryParams(BaseModel):
    """OData query parameters for filtering and shaping entity list results.

    All fields are optional. When omitted, the OData service applies its
    own defaults (usually no filter, no limit).

    Example usage by LLM:
        filter="Дата ge datetime'2026-05-01T00:00:00'"
        top=10
        select="Ref,Дата,Контрагент"
    """

    filter: str | None = Field(
        default=None,
        description=(
            "OData $filter expression. "
            "Example: \"Дата ge datetime'2026-05-01T00:00:00' "
            "and Дата le datetime'2026-05-31T23:59:59'\""
        ),
    )
    top: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of records to return (1–200, default 50).",
    )
    skip: int = Field(
        default=0,
        ge=0,
        description="Number of records to skip for pagination.",
    )
    select: str | None = Field(
        default=None,
        description=(
            "Comma-separated list of fields to return. "
            'Example: "Ref,Дата,Контрагент,СуммаДокумента"'
        ),
    )
    orderby: str | None = Field(
        default=None,
        description='OData $orderby expression. Example: "Дата desc"',
    )
    expand: str | None = Field(
        default=None,
        description=(
            "Comma-separated navigation properties to expand inline. "
            'Example: "Контрагент"'
        ),
    )


class EntityListResponse(BaseModel):
    """Response schema for entity list queries.

    Attributes:
        count: Number of items returned in this response (not the total
            count in the database — use ``$inlinecount`` for that).
        items: List of entity records as returned by 1C OData.
    """

    count: int = Field(description="Number of items in this response.")
    items: list[dict[str, Any]] = Field(description="Entity records.")


class EntityCreateResponse(BaseModel):
    """Response schema for entity creation.

    Attributes:
        item: The created entity record as returned by 1C OData,
            including server-generated fields (Ref, etc.).
    """

    item: dict[str, Any] = Field(description="Created entity record.")
