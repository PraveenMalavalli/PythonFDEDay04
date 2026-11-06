"""Expected JSON shapes for the demonstration API.

Change these models to match the real Training Mock API README when provided.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: int = Field(gt=0)
    name: str = Field(min_length=1)
    status: Literal["active", "inactive", "pending"]
    category: str = Field(min_length=1)
    created: date = Field(strict=False)


class APIMeta(BaseModel):
    entity: str
    pagination: Literal["page", "offset", "cursor"]
    total: int


class PageResult(BaseModel):
    items: list[Item]
    page: int
    page_size: int
    total: int
    has_more: bool


class OffsetResult(BaseModel):
    items: list[Item]
    offset: int
    limit: int
    total: int


class CursorResult(BaseModel):
    items: list[Item]
    next_cursor: str | None
