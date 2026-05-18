import sqlite3
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends

from src.application.use_cases.create_item import CreateItemUseCase
from src.application.use_cases.list_items import ListItemsUseCase
from src.infrastructure.database.connection import get_connection
from src.infrastructure.database.item_repository import SQLiteItemRepository

# Set once at application startup via set_db_path()
_db_path: str = "app.db"


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(_db_path)
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


def get_item_repository(conn: DbDep) -> SQLiteItemRepository:
    return SQLiteItemRepository(conn)


RepoDep = Annotated[SQLiteItemRepository, Depends(get_item_repository)]


def get_create_item_use_case(repo: RepoDep) -> CreateItemUseCase:
    return CreateItemUseCase(repo)


def get_list_items_use_case(repo: RepoDep) -> ListItemsUseCase:
    return ListItemsUseCase(repo)
