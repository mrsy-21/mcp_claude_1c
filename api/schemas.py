"""Pydantic schemas for FastAPI request/response validation."""

from typing import Any

from pydantic import BaseModel, Field


class EntityQueryParams(BaseModel):
    """OData query parameters — used by metadata router."""

    filter: str | None = Field(default=None)
    top: int = Field(default=50, ge=1, le=200)
    skip: int = Field(default=0, ge=0)
    orderby: str | None = Field(default=None)


class EntityListResponse(BaseModel):
    count: int
    items: list[dict[str, Any]]
