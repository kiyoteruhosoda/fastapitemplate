"""example コンテキストの API（Item CRUD）。

コンテキスト固有のルーター・スキーマ・依存関数は presentation/ 配下に
まとめる。認可は scope（``item:view`` / ``item:manage``）で宣言する。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from bounded_contexts.example.application.use_cases.create_item import CreateItemUseCase
from bounded_contexts.example.application.use_cases.list_items import ListItemsUseCase
from bounded_contexts.example.infrastructure.sql_item_repository import SqlItemRepository
from presentation.fastapi.dependencies.auth import require_permission
from shared.kernel.database.session import get_db

router = APIRouter(prefix="/api/items", tags=["items"])
logger = logging.getLogger(__name__)


class ItemCreateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


class ItemResponse(BaseModel):
    id: int
    name: str


def get_item_repository(
    db: Annotated[Session, Depends(get_db)],
) -> SqlItemRepository:
    return SqlItemRepository(db)


RepoDep = Annotated[SqlItemRepository, Depends(get_item_repository)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ItemResponse,
    dependencies=[Depends(require_permission("item:manage"))],
)
async def create_item(body: ItemCreateRequest, repo: RepoDep) -> ItemResponse:
    dto = CreateItemUseCase(repo).execute(body.name)
    logger.info("item_created", extra={"item_id": dto.id})
    return ItemResponse(id=dto.id, name=dto.name)


@router.get(
    "",
    response_model=list[ItemResponse],
    dependencies=[Depends(require_permission("item:view"))],
)
async def list_items(repo: RepoDep) -> list[ItemResponse]:
    dtos = ListItemsUseCase(repo).execute()
    return [ItemResponse(id=dto.id, name=dto.name) for dto in dtos]
