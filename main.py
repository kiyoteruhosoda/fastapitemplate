from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.infrastructure.database.connection import init_db
from src.infrastructure.logging.structured_logger import setup_logging
from src.presentation.api.dependencies import set_db_path
from src.presentation.api.routers import health, items
from src.presentation.middleware.logging_middleware import RequestLoggingMiddleware


def create_app(db_path: str = "app.db") -> FastAPI:
    setup_logging()
    set_db_path(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        init_db(db_path)
        yield

    app = FastAPI(
        title="FastAPI Template",
        version="0.1.0",
        description="FastAPI + SQLite template – Clean Architecture / DDD.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health.router)
    app.include_router(items.router)
    return app


app = create_app()
