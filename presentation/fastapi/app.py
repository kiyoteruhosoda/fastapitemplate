"""FastAPI アプリケーションファクトリ。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from bounded_contexts.account_security.presentation.error_handling import (
    register_account_security_error_handler,
)
from bounded_contexts.account_security.presentation.passkey_login_router import (
    router as passkey_login_router,
)
from bounded_contexts.account_security.presentation.router import (
    router as account_security_router,
)
from bounded_contexts.audit.presentation.log_retention import (
    start_log_retention_worker,
)
from bounded_contexts.audit.presentation.middleware import AuditRecordingMiddleware
from bounded_contexts.audit.presentation.router import (
    application_log_router as admin_logs_router,
)
from bounded_contexts.audit.presentation.router import (
    audit_log_router as admin_audit_logs_router,
)
from bounded_contexts.example.presentation.router import router as items_router
from bounded_contexts.identity_federation.presentation.error_handling import (
    register_identity_federation_error_handler,
)
from bounded_contexts.identity_federation.presentation.router import (
    router as sso_router,
)
from bounded_contexts.identity_federation.presentation.startup_check import (
    report_sso_configuration,
)
from presentation.fastapi.error_handling import register_error_handling
from presentation.fastapi.middleware.deferred_log_writes import (
    DeferredLogWriteMiddleware,
)
from presentation.fastapi.middleware.internal_error import InternalErrorMiddleware
from presentation.fastapi.middleware.request_logging import RequestLoggingMiddleware
from presentation.fastapi.routers import spa
from presentation.fastapi.routers.admin.config import router as admin_config_router
from presentation.fastapi.routers.admin.permissions import (
    router as admin_permissions_router,
)
from presentation.fastapi.routers.admin.roles import router as admin_roles_router
from presentation.fastapi.routers.admin.system import router as admin_system_router
from presentation.fastapi.routers.admin.users import router as admin_users_router
from presentation.fastapi.routers.auth import router as auth_router
from presentation.fastapi.routers.health import router as health_router
from presentation.fastapi.routers.ui_settings import router as ui_settings_router
from shared.kernel.logging.logging_config import setup_logging
from shared.kernel.restart import (
    RestartScope,
    start_restart_watcher,
    stop_restart_watchers,
)
from shared.kernel.scheduling import stop_interval_workers
from shared.kernel.settings.settings import settings
from shared.kernel.version import load_build_info


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # 管理画面からの再起動要求を拾う（起動時にしか読まれない設定の反映用）
    start_restart_watcher(RestartScope.WEB)
    # 保持期間を過ぎたログを定期的に消す（既定は削除しない。ADR-0021）
    start_log_retention_worker()
    # SSO の設定が実際に使えるかを一度だけ確かめる（秘密鍵は署名のときまで読まれない
    # ため、権限の食い違いが利用者の戻りでしか出ない。ADR-0025）
    report_sso_configuration()
    try:
        yield
    finally:
        stop_interval_workers()
        stop_restart_watchers()


def _include_routers(app: FastAPI) -> None:
    """ルーターの登録。**SPA より前**に並べる（SPA は catch-all のため）。"""
    for router in (
        health_router,
        ui_settings_router,
        auth_router,
        passkey_login_router,
        account_security_router,
        sso_router,
        admin_users_router,
        admin_roles_router,
        admin_permissions_router,
        admin_config_router,
        admin_logs_router,
        admin_audit_logs_router,
        admin_system_router,
        items_router,
    ):
        app.include_router(router)


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
        lifespan=_lifespan,
    )
    app.state.build_info = build_info
    app.state.startup_time = datetime.now(UTC)

    # Prometheus metrics at /metrics
    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app, include_in_schema=False)

    # ログ・監査の DB 書き込みは、リクエストの DB セッションが閉じた後に行う
    # （途中で書くと SQLite でロックが競合する。ADR-0013）。
    #
    # 後から追加したものが外側になる。外側から
    # DeferredLogWrite → RequestLogging → AuditRecording → InternalError の順で、
    # アクセスログ（RequestLogging が出す）もログのまとめ書きに載る
    # ＝ 1 リクエストあたりの INSERT は 2 回（log と audit_log）に収まる。
    #
    # 想定外の例外を応答へ変える層は最も内側に置く。ここで受け止めないと例外は
    # 全ミドルウェアを飛び越え、アクセスログの 500 の行も、そのリクエストで出た
    # ログ行のまとめ書きも失われる。
    app.add_middleware(InternalErrorMiddleware)
    app.add_middleware(AuditRecordingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(DeferredLogWriteMiddleware)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 失敗の記録（4xx・入力検証）と、ミドルウェアより外側で落ちたとき用の保険。
    # 個別のドメイン例外ハンドラが優先される。
    register_error_handling(app)
    register_account_security_error_handler(app)
    register_identity_federation_error_handler(app)

    _include_routers(app)

    # SPA は最後（catch-all のため）。ビルド済みの場合のみ配信する。
    if spa.dist_available():
        app.include_router(spa.router)

    return app


__all__ = ["create_app"]
