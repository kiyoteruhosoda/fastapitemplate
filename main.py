from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3

from fastapi import FastAPI, status
from pydantic import BaseModel


class ItemCreate(BaseModel):
    name: str


class Item(BaseModel):
    id: int
    name: str


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Path) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
            """
        )


def create_app(db_path: str = "app.db") -> FastAPI:
    database_path = Path(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(database_path)
        yield

    app = FastAPI(
        title="FastAPI Template",
        version="0.1.0",
        description="FastAPI + SQLite template for uv development and Docker deployment.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
    def create_item(payload: ItemCreate) -> Item:
        with _connect(database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO items (name) VALUES (?)",
                (payload.name,),
            )
            item_id = cursor.lastrowid
            row = connection.execute(
                "SELECT id, name FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()
        return Item.model_validate(dict(row))

    @app.get("/items", response_model=list[Item])
    def list_items() -> list[Item]:
        with _connect(database_path) as connection:
            rows = connection.execute(
                "SELECT id, name FROM items ORDER BY id ASC"
            ).fetchall()
        return [Item.model_validate(dict(row)) for row in rows]

    return app


app = create_app()
