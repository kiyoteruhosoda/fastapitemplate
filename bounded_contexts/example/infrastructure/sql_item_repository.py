"""``IItemRepository`` の SQLAlchemy 実装。

テナントの中身の見本（ADR-0079 §1 決定 5）。**テナントはコンストラクタで受け取り**、
読み書きのすべてをそのテナントで絞る。メソッドの引数にはしない ——呼び側が渡し忘れる
余地を作らないため。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bounded_contexts.example.domain.entities.item import Item
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
        validated_name = ItemName(name)  # ドメイン不変条件を DB 書き込み前に強制する
        row = ItemModel(tenant_id=self._tenant_id, name=validated_name.value)
        self._session.add(row)
        self._session.flush()
        return Item(id=row.id, name=validated_name)

    def find_page(self, order: ItemListOrder, page: PageRequest) -> Page[Item]:
        owned = ItemModel.tenant_id == self._tenant_id
        rows = self._session.scalars(
            select(ItemModel).where(owned).order_by(*_ORDER_BY[order]).limit(page.limit).offset(page.offset)
        ).all()
        total = self._session.scalar(select(func.count()).select_from(ItemModel).where(owned))
        return Page(entries=[Item.create(id=row.id, name=row.name) for row in rows], total=total or 0)
