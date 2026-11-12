"""SQLAlchemy implementation of ``IItemRepository``.

Sample of tenant content (ADR-0079 §1 decision 5). **The tenant is taken in the constructor**
and every read and write is filtered by it. It is not a method argument, so callers have
no chance to forget to pass it.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bounded_contexts.example.domain.entities.item import Item
from bounded_contexts.example.domain.exceptions import ItemNotFoundError
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder
from bounded_contexts.example.domain.value_objects.item_name import ItemName
from bounded_contexts.example.infrastructure.item_model import ItemModel
from shared.domain.page import Page, PageRequest

_ORDER_BY = {
    ItemListOrder.OLDEST: (ItemModel.id,),
    ItemListOrder.NEWEST: (ItemModel.id.desc(),),
    ItemListOrder.NAME: (ItemModel.name, ItemModel.id),
}


class SqlItemRepository(IItemRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def save(self, name: str) -> Item:
        validated_name = ItemName(name)  # enforce the domain invariant before writing to the DB
        row = ItemModel(tenant_id=self._tenant_id, name=validated_name.value)
        self._session.add(row)
        self._session.flush()
        return _to_entity(row)

    def rename(self, item_id: int, name: str) -> Item:
        validated_name = ItemName(name)
        row = self._owned_row(item_id)
        row.name = validated_name.value
        self._session.flush()
        return _to_entity(row)

    def delete(self, item_id: int) -> None:
        self._session.delete(self._owned_row(item_id))
        self._session.flush()

    def _owned_row(self, item_id: int) -> ItemModel:
        row = self._session.scalar(
            select(ItemModel).where(ItemModel.id == item_id, ItemModel.tenant_id == self._tenant_id)
        )
        if row is None:
            raise ItemNotFoundError
        return row

    def find_page(self, order: ItemListOrder, page: PageRequest) -> Page[Item]:
        owned = ItemModel.tenant_id == self._tenant_id
        rows = self._session.scalars(
            select(ItemModel).where(owned).order_by(*_ORDER_BY[order]).limit(page.limit).offset(page.offset)
        ).all()
        total = self._session.scalar(select(func.count()).select_from(ItemModel).where(owned))
        return Page(entries=[_to_entity(row) for row in rows], total=total or 0)


def _to_entity(row: ItemModel) -> Item:
    return Item(id=row.id, name=ItemName(row.name), created_at=row.created_at, updated_at=row.updated_at)
