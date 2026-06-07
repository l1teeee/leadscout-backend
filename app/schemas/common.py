from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_PAGE_LIMIT = 200


class PaginationParams(BaseModel):
    limit: int = Field(50, ge=1, le=MAX_PAGE_LIMIT)
    offset: int = Field(0, ge=0)


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    total: int
    limit: int
    offset: int
