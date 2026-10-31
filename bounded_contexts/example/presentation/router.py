"""example コンテキストの API（Item CRUD）。

コンテキスト固有のルーター・スキーマ・依存関数は presentation/ 配下に
まとめる。認可は scope（``item:view`` / ``item:write``）で宣言する。

一覧の並び順はテナントのコンテンツ設定 ``item_list_order`` に従う（コンテンツ設定を読む見本。ADR-0085）。
一覧はページで返す（一覧 API の規約の見本。ADR-0095）。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from bounded_contexts.content_settings.application.use_cases.content_settings_book import ContentSettingsBook
from bounded_contexts.content_settings.domain.definitions import ITEM_LIST_ORDER
from bounded_contexts.content_settings.presentation.router import get_content_settings_book
from bounded_contexts.example.application.dto.item_dto import ItemDTO
from bounded_contexts.example.application.use_cases.create_item import CreateItemUseCase
from bounded_contexts.example.application.use_cases.delete_item import DeleteItemUseCase
from bounded_contexts.example.application.use_cases.list_items import ListItemsUseCase
from bounded_contexts.example.application.use_cases.update_item import UpdateItemUseCase
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder
from bounded_contexts.example.infrastructure.sql_item_repository import SqlItemRepository
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.dependencies.tenant import TenantIdDep
from presentation.fastapi.schemas.pagination import PageQueryRequest, PageResponse
from shared.kernel.database.session import get_db
from shared.kernel.timestamps import isoformat_utc

router = APIRouter(prefix="/api/items", tags=["items"])
logger = logging.getLogger(__name__)


class ItemRequest(BaseModel):
    name: str = Field(max_length=255)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


class ItemResponse(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, dto: ItemDTO) -> ItemResponse:
        return cls(
            id=dto.id,
            name=dto.name,
            created_at=isoformat_utc(dto.created_at),
            updated_at=isoformat_utc(dto.updated_at),
        )


def get_item_repository(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: TenantIdDep,
) -> SqlItemRepository:
    return SqlItemRepository(db, tenant_id)


RepoDep = Annotated[SqlItemRepository, Depends(get_item_repository)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ItemResponse,
    dependencies=[Depends(require_permission("item:write"))],
)
async def create_item(body: ItemRequest, repo: RepoDep) -> ItemResponse:
    dto = CreateItemUseCase(repo).execute(body.name)
    logger.info("item_created", extra={"item_id": dto.id})
    return ItemResponse.of(dto)


@router.get(
    "",
    response_model=PageResponse[ItemResponse],
    dependencies=[Depends(require_permission("item:view"))],
)
async def list_items(
    query: Annotated[PageQueryRequest, Query()],
    repo: RepoDep,
    settings: Annotated[ContentSettingsBook, Depends(get_content_settings_book)],
) -> PageResponse[ItemResponse]:
    # 選択の項目なので値は選べる値のどれか（合わない値は既定値で読む）
    order = ItemListOrder(str(settings.value_of(ITEM_LIST_ORDER)))
    page = ListItemsUseCase(repo).execute(order, query.to_page())
    return PageResponse(entries=[ItemResponse.of(dto) for dto in page.entries], total=page.total)


@router.put(
    "/{item_id}",
    response_model=ItemResponse,
    dependencies=[Depends(require_permission("item:write"))],
)
async def update_item(item_id: int, body: ItemRequest, repo: RepoDep) -> ItemResponse:
    dto = UpdateItemUseCase(repo).execute(item_id, body.name)
    logger.info("item_updated", extra={"item_id": item_id})
    return ItemResponse.of(dto)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("item:write"))],
)
async def delete_item(item_id: int, repo: RepoDep) -> None:
    DeleteItemUseCase(repo).execute(item_id)
    logger.info("item_deleted", extra={"item_id": item_id})
