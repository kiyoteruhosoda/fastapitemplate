"""ヘルスチェック・運用プローブ（k8s / Docker healthcheck 用）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.kernel.database.session import get_db

router = APIRouter(tags=["ops"])


class LivenessResponse(BaseModel):
    status: str
    version: str
    timestamp_utc: str
    uptime_seconds: float


class ReadinessResponse(BaseModel):
    status: str
    # key = チェック名, value = "ok" | "ng"。依存が増えたらここへ追加する
    checks: dict[str, str]
    timestamp_utc: str


class InfoResponse(BaseModel):
    version: str
    git_sha: str
    branch: str
    build_time: str
    environment: str


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/healthz", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(request: Request) -> LivenessResponse:
    now = datetime.now(UTC)
    build_info = request.app.state.build_info
    startup_time = request.app.state.startup_time
    return LivenessResponse(
        status="ok",
        version=build_info.version,
        timestamp_utc=now.isoformat(),
        uptime_seconds=(now - startup_time).total_seconds(),
    )


@router.get("/readyz", summary="Readiness probe")
async def readiness(
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    now = datetime.now(UTC)
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "ng"

    all_ok = all(v == "ok" for v in checks.values())
    body = ReadinessResponse(
        status="ok" if all_ok else "ng",
        checks=checks,
        timestamp_utc=now.isoformat(),
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body.model_dump(),
    )


@router.get("/info", response_model=InfoResponse, summary="Build / version info")
async def info(request: Request) -> InfoResponse:
    build_info = request.app.state.build_info
    return InfoResponse(
        version=build_info.version,
        git_sha=build_info.git_sha,
        branch=build_info.branch,
        build_time=build_info.build_time,
        environment=build_info.environment,
    )
