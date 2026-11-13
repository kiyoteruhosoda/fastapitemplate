"""API for system status (requires ``system:view``) and application restart (requires
``system:manage``).

Accepts restart requests so settings read only at startup (logging, CORS, etc.) can be applied
from the admin console. A request is stored in the DB; each process checks whether it is the
target and terminates itself. Recovery is left to the container's restart policy
(:mod:`shared.kernel.restart`).

This aborts all in-flight requests, so every request is recorded in the audit log.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import (
    RestartCommandRequest,
    RestartCommandResponse,
    RestartRequestResponse,
    RestartStatusResponse,
    SystemStatusResponse,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.restart import (
    ALL_RESTART_SCOPES,
    RestartRequest,
    RestartRequestStore,
    RestartScope,
)
from shared.kernel.timestamps import isoformat_utc, utcnow_aware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/system", tags=["admin"])

DbDep = Annotated[Session, Depends(get_db)]
SystemManagerDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("system:manage"))]
#: Viewing status only. Support staff have it too (ADR-0084 §3)
SystemViewerDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("system:view"))]


def _to_response(request: RestartRequest) -> RestartRequestResponse:
    return RestartRequestResponse(
        scope=request.scope.value,
        token=request.token,
        requested_at=(isoformat_utc(request.requested_at) if request.requested_at else None),
        requested_by=request.requested_by,
        reason=request.reason,
    )


@router.get("/status", response_model=SystemStatusResponse)
def system_status(request: Request, _principal: SystemViewerDep, db: DbDep) -> SystemStatusResponse:
    """Return build info and the status of each component (API, DB).

    Reaching this handler means the API itself is responding, so ``api`` is always ``ok``.
    The DB is checked with the same ``SELECT 1`` as ``/readyz``.
    """
    now = utcnow_aware()
    build_info = request.app.state.build_info
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "ng"
    return SystemStatusResponse(
        version=build_info.version,
        git_sha=build_info.git_sha,
        branch=build_info.branch,
        build_time=build_info.build_time,
        environment=build_info.environment,
        components={"api": "ok", "database": database},
        uptime_seconds=(now - request.app.state.startup_time).total_seconds(),
        timestamp_utc=isoformat_utc(now),
    )


@router.get("/restart", response_model=RestartStatusResponse)
async def restart_status(_principal: SystemManagerDep) -> RestartStatusResponse:
    """Return the latest restart request per scope and the list of selectable scopes."""
    stored = RestartRequestStore().load_all()
    return RestartStatusResponse(
        available_scopes=[scope.value for scope in ALL_RESTART_SCOPES],
        last_requests=[_to_response(stored[scope]) for scope in ALL_RESTART_SCOPES if scope in stored],
    )


@router.post(
    "/restart",
    response_model=RestartCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_restart(
    body: RestartCommandRequest,
    principal: SystemManagerDep,
    db: DbDep,
    audit: AuditRecorderDep,
) -> RestartCommandResponse:
    """Request a restart.

    If ``scopes`` is omitted, all services are targeted. A watcher thread picks up and handles
    the request, so the restart has not happened yet when the response returns.
    """
    if body.scopes is None:
        scopes: tuple[RestartScope, ...] = ALL_RESTART_SCOPES
    else:
        scopes = RestartScope.parse_all(body.scopes)
        if not scopes:
            audit.execute(
                AuditEventType.SERVICE_RESTART_REQUESTED,
                AuditResult.FAILURE,
                target=AuditTarget.of(AuditTargetType.SERVICE),
                reason="invalid_restart_scope",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_restart_scope"},
            )

    reason = body.reason.strip() if body.reason and body.reason.strip() else None
    try:
        requests = RestartRequestStore().save(
            db,
            scopes,
            # The requester also ends up in logs, so record a principal identifier without PII
            requested_by=f"user:{principal.user_id}",
            reason=reason,
        )
    except Exception:
        logger.exception("Failed to save restart request")
        audit.execute(
            AuditEventType.SERVICE_RESTART_REQUESTED,
            AuditResult.FAILURE,
            target=AuditTarget.of(AuditTargetType.SERVICE),
            reason="restart_request_failed",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "restart_request_failed"},
        ) from None

    audit.execute(
        AuditEventType.SERVICE_RESTART_REQUESTED,
        target=AuditTarget.of(AuditTargetType.SERVICE, ",".join(scope.value for scope in scopes)),
        reason=reason,
    )
    return RestartCommandResponse(requested=True, requests=[_to_response(request) for request in requests])
