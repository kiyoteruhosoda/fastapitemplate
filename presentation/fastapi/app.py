"""FastAPI アプリケーションファクトリ。"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from bounded_contexts.example.presentation.router import router as items_router
from presentation.fastapi.middleware.request_logging import RequestLoggingMiddleware
from presentation.fastapi.routers import spa
from presentation.fastapi.routers.admin.config import router as admin_config_router
from presentation.fastapi.routers.admin.logs import router as admin_logs_router
from presentation.fastapi.routers.admin.maintenance import (
    router as admin_maintenance_router,
)
from presentation.fastapi.routers.admin.permissions import (
    router as admin_permissions_router,
)
from presentation.fastapi.routers.admin.roles import router as admin_roles_router
from presentation.fastapi.routers.admin.users import router as admin_users_router
from presentation.fastapi.routers.auth import router as auth_router
from presentation.fastapi.routers.health import router as health_router
from shared.kernel.logging.logging_config import setup_logging
from shared.kernel.settings.settings import settings
from shared.kernel.version import load_build_info


def create_app() -> FastAPI:
    setup_logging(
        level=settings.log_level,
        database=settings.log_to_database and not settings.testing,
    )

    build_info = load_build_info()
    app = FastAPI(
        title="fastapitemplate",
        version=build_info.version,
        description="FastAPI + DDD template (photonest-based).",
    )
    app.state.build_info = build_info
    app.state.startup_time = datetime.now(UTC)

    # Prometheus metrics at /metrics
    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(
        app, include_in_schema=False
    )

    app.add_middleware(RequestLoggingMiddleware)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_users_router)
    app.include_router(admin_roles_router)
    app.include_router(admin_permissions_router)
    app.include_router(admin_config_router)
    app.include_router(admin_logs_router)
    app.include_router(admin_maintenance_router)
    app.include_router(items_router)

    # SPA は最後（catch-all のため）。ビルド済みの場合のみ配信する。
    if spa.dist_available():
        app.include_router(spa.router)

    return app


__all__ = ["create_app"]
