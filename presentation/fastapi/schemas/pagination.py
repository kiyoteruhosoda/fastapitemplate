"""Common shape of list APIs (ADR-0095)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from shared.domain.page import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PageRequest


class PageQueryRequest(BaseModel):
    """Received as ``Annotated[PageQueryRequest, Query()]``. Values over the limit get 422."""

    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0)

    def to_page(self) -> PageRequest:
        return PageRequest(limit=self.limit, offset=self.offset)


class PageResponse[T](BaseModel):
    entries: list[T]
    #: Total count, not the count on this page
    total: int


__all__ = ["PageQueryRequest", "PageResponse"]
