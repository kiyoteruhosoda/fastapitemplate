import sqlite3

from src.domain.entities.item import Item
from src.domain.repositories.item_repository import IItemRepository


class SQLiteItemRepository(IItemRepository):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, name: str) -> Item:
        cursor = self._conn.execute(
            "INSERT INTO items (name) VALUES (?)", (name,)
        )
        self._conn.commit()
        return Item.create(id=cursor.lastrowid, name=name)

    def find_all(self) -> list[Item]:
        rows = self._conn.execute(
            "SELECT id, name FROM items ORDER BY id"
        ).fetchall()
        return [Item.create(id=row["id"], name=row["name"]) for row in rows]
