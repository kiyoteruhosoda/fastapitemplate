"""``IItemRepository`` の SQLAlchemy 実装。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.example.domain.entities.item import Item
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository
from bounded_contexts.example.domain.value_objects.item_name import ItemName
from bounded_contexts.example.infrastructure.item_model import ItemModel


class SqlItemRepository(IItemRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, name: str) -> Item:
        validated_name = ItemName(name)  # ドメイン不変条件を DB 書き込み前に強制する
        row = ItemModel(name=validated_name.value)
        self._session.add(row)
        self._session.flush()
        return Item(id=row.id, name=validated_name)

    def find_all(self) -> list[Item]:
        rows = self._session.scalars(select(ItemModel).order_by(ItemModel.id)).all()
        return [Item.create(id=row.id, name=row.name) for row in rows]
