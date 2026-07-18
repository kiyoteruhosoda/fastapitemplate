"""メンテナンス API（要 ``system:manage``）。"""
from __future__ import annotations

import os
import signal

from fastapi import APIRouter, Depends, status

from presentation.fastapi.dependencies.auth import require_permission

router = APIRouter(
    prefix="/api/admin/maintenance",
    tags=["admin"],
    dependencies=[Depends(require_permission("system:manage"))],
)


@router.post(
    "/shutdown",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Graceful shutdown",
    description="プロセスへ SIGTERM を送り、ASGI サーバーの graceful shutdown を開始する。",
)
async def shutdown() -> dict[str, str]:
    os.kill(os.getpid(), signal.SIGTERM)
    return {"message": "shutdown initiated"}
