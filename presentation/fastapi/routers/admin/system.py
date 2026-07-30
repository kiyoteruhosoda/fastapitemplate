"""アプリケーション再起動 API（要 ``system:manage``）。

起動時にしか読まれない設定（ログ・CORS 等）を管理画面から反映するための
再起動要求を受け付ける。要求は DB に置かれ、各プロセスが自分宛かを判定して
自らを終了させる。復帰はコンテナの restart policy に任せる
（:mod:`shared.kernel.restart`）。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.schemas.admin import (
    RestartCommandRequest,
    RestartCommandResponse,
    RestartRequestResponse,
    RestartStatusResponse,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.restart import (
    ALL_RESTART_SCOPES,
    RestartRequest,
    RestartRequestStore,
    RestartScope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/system", tags=["admin"])

DbDep = Annotated[Session, Depends(get_db)]
SystemManagerDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("system:manage"))]


def _to_response(request: RestartRequest) -> RestartRequestResponse:
    return RestartRequestResponse(
        scope=request.scope.value,
        token=request.token,
        requested_at=(request.requested_at.isoformat() if request.requested_at else None),
        requested_by=request.requested_by,
        reason=request.reason,
    )


@router.get("/restart", response_model=RestartStatusResponse)
async def restart_status(_principal: SystemManagerDep) -> RestartStatusResponse:
    """スコープごとの直近の再起動要求と、指定できるスコープの一覧を返す。"""
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
async def request_restart(
    body: RestartCommandRequest,
    principal: SystemManagerDep,
    db: DbDep,
) -> RestartCommandResponse:
    """再起動を要求する。

    ``scopes`` を省略した場合は全サービスが対象。要求は監視スレッドが拾って
    処理するため、応答が返った時点ではまだ再起動していない。
    """
    if body.scopes is None:
        scopes: tuple[RestartScope, ...] = ALL_RESTART_SCOPES
    else:
        scopes = RestartScope.parse_all(body.scopes)
        if not scopes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_restart_scope"},
            )

    reason = body.reason.strip() if body.reason and body.reason.strip() else None
    try:
        requests = RestartRequestStore().save(
            db,
            scopes,
            # 要求者はログにも残るため、PII を含まない主体識別子を記録する
            requested_by=f"user:{principal.user_id}",
            reason=reason,
        )
    except Exception:
        logger.exception("再起動要求の保存に失敗しました")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "restart_request_failed"},
        ) from None

    return RestartCommandResponse(requested=True, requests=[_to_response(request) for request in requests])
