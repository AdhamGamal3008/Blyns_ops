"""Shared response envelope, pagination, and base document fields
(docs/BUILD.md §5 cross-cutting conventions).

Success envelope:  { "data": {...}, "meta": { "page": 1, "page_size": 25, "total": 0 } }
Errors are rendered by app/core/errors.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Query
from pydantic import BaseModel

MAX_PAGE_SIZE = 100


def envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def page_meta(page: int, page_size: int, total: int) -> dict[str, int]:
    return {"page": page, "page_size": page_size, "total": total}


class PaginationParams(BaseModel):
    """FastAPI dependency: `params: PaginationParams = Depends()`."""

    page: int = Query(default=1, ge=1)
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


class BaseDocFields(BaseModel):
    """Fields every persisted document carries (docs/BUILD.md §5).

    Mongo ObjectId internally; exposed as string `id` in API bodies.
    Soft delete only — hard delete happens solely via provisioning teardown.
    """

    id: str
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
