"""Health checks and operational probes (for k8s / Docker healthcheck)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.kernel.database.session import get_db
from shared.kernel.timestamps import isoformat_utc, utcnow_aware

router = APIRouter(tags=["ops"])


class LivenessResponse(BaseModel):
    status: str
    version: str
    timestamp_utc: str
    uptime_seconds: float


class ReadinessResponse(BaseModel):
    status: str
    # key = check name, value = "ok" | "ng". Add new dependencies here
    checks: dict[str, str]
    timestamp_utc: str


class InfoResponse(BaseModel):
    """Only the version, readable unauthenticated (ADR-0096). Branch, build time and environment
    name are in ``/api/admin/system``."""

    version: str
    git_sha: str


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/healthz", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(request: Request) -> LivenessResponse:
    now = utcnow_aware()
    build_info = request.app.state.build_info
    startup_time = request.app.state.startup_time
    return LivenessResponse(
        status="ok",
        version=build_info.version,
        timestamp_utc=isoformat_utc(now),
        uptime_seconds=(now - startup_time).total_seconds(),
    )


@router.get("/readyz", summary="Readiness probe")
def readiness(
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    now = utcnow_aware()
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
        timestamp_utc=isoformat_utc(now),
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body.model_dump(),
    )


@router.get("/info", response_model=InfoResponse, summary="Build / version info")
async def info(request: Request) -> InfoResponse:
    build_info = request.app.state.build_info
    return InfoResponse(version=build_info.version, git_sha=build_info.git_sha)
