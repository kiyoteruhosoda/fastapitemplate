"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
from bounded_contexts.app_release.presentation.router import router as app_release_router
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
from bounded_contexts.content_settings.presentation.router import router as content_settings_router
from bounded_contexts.example.presentation.error_handling import register_item_error_handler
from bounded_contexts.example.presentation.router import router as items_router
from bounded_contexts.identity_federation.presentation.error_handling import (
    register_identity_federation_error_handler,
)
from bounded_contexts.identity_federation.presentation.machine_router import (
    router as machine_router,
)
from bounded_contexts.identity_federation.presentation.reconciliation import (
    start_sso_reconciliation_worker,
)
from bounded_contexts.identity_federation.presentation.router import (
    router as sso_router,
)
from bounded_contexts.identity_federation.presentation.startup_check import (
    report_machine_entrance,
    report_sso_configuration,
)
from bounded_contexts.notes.presentation.error_handling import register_note_error_handler
from bounded_contexts.notes.presentation.router import router as notes_router
from bounded_contexts.notification.presentation.error_handling import (
    register_notification_error_handler,
)
from bounded_contexts.notification.presentation.router import (
    admin_router as admin_notifications_router,
)
from bounded_contexts.notification.presentation.router import (
    router as notifications_router,
)
from presentation.fastapi.error_handling import register_error_handling
from presentation.fastapi.middleware.csrf import CsrfMiddleware
from presentation.fastapi.middleware.deferred_log_writes import (
    DeferredLogWriteMiddleware,
)
from presentation.fastapi.middleware.internal_error import InternalErrorMiddleware
from presentation.fastapi.middleware.request_logging import RequestLoggingMiddleware
from presentation.fastapi.middleware.security_headers import SecurityHeadersMiddleware
from presentation.fastapi.routers import spa
from presentation.fastapi.routers.admin.config import router as admin_config_router
from presentation.fastapi.routers.admin.groups import router as admin_groups_router
from presentation.fastapi.routers.admin.permissions import (
    router as admin_permissions_router,
)
from presentation.fastapi.routers.admin.roles import router as admin_roles_router
from presentation.fastapi.routers.admin.system import router as admin_system_router
from presentation.fastapi.routers.admin.users import router as admin_users_router
from presentation.fastapi.routers.app_links import router as app_links_router
from presentation.fastapi.routers.app_session import router as app_session_router
from presentation.fastapi.routers.auth import router as auth_router
from presentation.fastapi.routers.health import router as health_router
from presentation.fastapi.routers.system.administrators import router as system_administrators_router
from presentation.fastapi.routers.system.tenants import router as system_tenants_router
from presentation.fastapi.routers.ui_settings import router as ui_settings_router
from presentation.fastapi.services.password_token_purge import start_password_token_purge_worker
from shared.kernel.logging.logging_config import setup_logging
from shared.kernel.restart import (
    RestartScope,
    start_restart_watcher,
    stop_restart_watchers,
)
from shared.kernel.scheduling import stop_interval_workers
from shared.kernel.settings.secret_guard import require_usable_secret
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow_aware
from shared.kernel.version import load_build_info


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Pick up restart requests from the admin console (to apply settings read only at startup)
    start_restart_watcher(RestartScope.WEB)
    # Periodically delete logs past their retention (no deletion by default; ADR-0075 §3)
    start_log_retention_worker()
    # Delete unusable password reset tokens (ADR-0097)
    start_password_token_purge_worker()
    # Re-check hourly and end SSO sessions of people suspended at the IdP
    # (does nothing if MACHINE_CLIENT_ID is empty; ADR-0077 §7)
    start_sso_reconciliation_worker()
    # Check once that the SSO configuration actually works (the private key isn't read until
    # signing, so a permission mismatch would otherwise only surface on a user's return;
    # ADR-0077 §1)
    report_sso_configuration()
    report_machine_entrance()
    try:
        yield
    finally:
        stop_interval_workers()
        stop_restart_watchers()


def _include_routers(app: FastAPI) -> None:
    """Register routers. They go **before the SPA** (the SPA is a catch-all)."""
    for router in (
        health_router,
        app_links_router,
        app_session_router,
        app_release_router,
        ui_settings_router,
        auth_router,
        passkey_login_router,
        account_security_router,
        sso_router,
        machine_router,
        admin_users_router,
        admin_roles_router,
        admin_permissions_router,
        admin_groups_router,
        admin_config_router,
        admin_logs_router,
        admin_audit_logs_router,
        admin_system_router,
        notifications_router,
        admin_notifications_router,
        system_tenants_router,
        system_administrators_router,
        content_settings_router,
        items_router,
        notes_router,
    ):
        app.include_router(router)


def create_app() -> FastAPI:
    setup_logging(
        level=settings.log_level,
        database=settings.log_to_database and not settings.testing,
    )

    build_info = load_build_info()
    # Abort startup here if production uses the default signing key (ADR-0073 §4)
    require_usable_secret(settings.jwt_secret_key, build_info.environment)
    app = FastAPI(
        # ⚠ Don't hard-code the name. Derive it from `[project].name` in `pyproject.toml`
        #   (ADR-0073 §2). Otherwise Swagger of apps built from the template keeps showing
        #   the template's name.
        title=build_info.name,
        version=build_info.version,
        description="FastAPI + DDD template (photonest-based).",
        lifespan=_lifespan,
    )
    app.state.build_info = build_info
    app.state.startup_time = utcnow_aware()

    # Prometheus metrics at /metrics
    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app, include_in_schema=False)

    # Log and audit DB writes happen after the request's DB session is closed
    # (writing midway causes lock contention on SQLite; ADR-0075 §1).
    #
    # Middleware added later is outer. From the outside the order is
    # DeferredLogWrite -> RequestLogging -> AuditRecording -> InternalError, so the access log
    # (emitted by RequestLogging) also goes into the batched write
    # = at most 2 INSERTs per request (log and audit_log).
    #
    # The layer that turns unexpected exceptions into responses goes innermost. Otherwise the
    # exception skips all middleware, and both the access log's 500 line and the batched log
    # rows from that request are lost.
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

    # Require the CSRF double-submit token for cookie-authenticated state-changing requests
    # (ADR-0076 §4). Not required for requests with an ``Authorization`` header (headers are not
    # sent automatically, so CSRF is not possible).
    app.add_middleware(CsrfMiddleware)

    # Protective headers (CSP, no framing, etc.; ADR-0073 §5). Outermost, so responses rejected
    # by CSRF get them too.
    app.add_middleware(SecurityHeadersMiddleware)

    # Records failures (4xx, input validation) and is a safety net for errors outside the
    # middleware. Specific domain exception handlers take precedence.
    register_error_handling(app)
    register_account_security_error_handler(app)
    register_identity_federation_error_handler(app)
    register_notification_error_handler(app)
    register_note_error_handler(app)
    register_item_error_handler(app)

    _include_routers(app)

    # SPA goes last (it is a catch-all). Served only if built.
    if spa.dist_available():
        app.include_router(spa.router)

    return app


__all__ = ["create_app"]
