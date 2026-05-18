from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.infrastructure.build_info import load_build_info
from src.infrastructure.database.connection import init_db
from src.infrastructure.logging.structured_logger import setup_logging
from src.presentation.api.dependencies import set_db_path
from src.presentation.api.routers import admin, health, items, ops
from src.presentation.middleware.logging_middleware import RequestLoggingMiddleware


def create_app(db_path: str = "app.db") -> FastAPI:
    setup_logging()
    set_db_path(db_path)

    build_info = load_build_info()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        init_db(db_path)
        yield

    app = FastAPI(
        title="FastAPI Template",
        version=build_info.version,
        description="FastAPI + SQLite template – Clean Architecture / DDD.",
        lifespan=lifespan,
    )

    # State available to all route handlers via request.app.state
    app.state.build_info = build_info
    app.state.startup_time = datetime.now(UTC)

    # Prometheus metrics at /metrics – excluded from its own tracking
    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(
        app, include_in_schema=False
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(health.router)
    app.include_router(ops.router)
    app.include_router(admin.router)
    app.include_router(items.router)
    return app


app = create_app()
