import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.presentation.api.dependencies import get_db
from src.presentation.api.schemas.ops import InfoResponse, LivenessResponse, ReadinessResponse

router = APIRouter(tags=["ops"])


@router.get(
    "/healthz",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Always returns 200 while the process is running. Use for k8s livenessProbe.",
)
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


@router.get(
    "/readyz",
    summary="Readiness probe",
    description=(
        "Returns 200 when all subsystems are ready, 503 otherwise. "
        "Use for k8s readinessProbe. Extend `checks` dict for each new dependency."
    ),
)
async def readiness(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> JSONResponse:
    now = datetime.now(UTC)

    # ── subsystem checks ────────────────────────────────────────────────────
    # Add more checks here as needed (cache, external APIs, etc.)
    checks: dict[str, str] = {}

    try:
        conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "ng"

    # ── aggregate result ────────────────────────────────────────────────────
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


@router.get(
    "/info",
    response_model=InfoResponse,
    summary="Build / version info",
    description="Returns version, git SHA, build timestamp, and runtime environment.",
)
async def info(request: Request) -> InfoResponse:
    build_info = request.app.state.build_info
    return InfoResponse(
        version=build_info.version,
        git_sha=build_info.git_sha,
        build_time=build_info.build_time,
        environment=build_info.environment,
    )
