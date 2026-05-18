import sqlite3

from src.domain.entities.item import Item
from src.domain.repositories.item_repository import IItemRepository
from src.domain.value_objects.item_name import ItemName


class SQLiteItemRepository(IItemRepository):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, name: str) -> Item:
        validated_name = ItemName(name)  # enforce domain invariants before any DB write
        cursor = self._conn.execute(
            "INSERT INTO items (name) VALUES (?)", (validated_name.value,)
        )
        self._conn.commit()
        return Item(id=cursor.lastrowid, name=validated_name)

    def find_all(self) -> list[Item]:
        rows = self._conn.execute(
            "SELECT id, name FROM items ORDER BY id"
        ).fetchall()
        return [Item.create(id=row["id"], name=row["name"]) for row in rows]
