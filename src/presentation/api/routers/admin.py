import os
import signal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_token(
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.getenv("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin endpoint is disabled. Set ADMIN_TOKEN env var to enable.",
        )
    if x_admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )


@router.post(
    "/shutdown",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Graceful shutdown",
    description=(
        "Sends SIGTERM to the process, triggering uvicorn graceful shutdown. "
        "Requires `X-Admin-Token` header matching `ADMIN_TOKEN` env var. "
        "Endpoint is disabled (403) when `ADMIN_TOKEN` is not set."
    ),
    dependencies=[Depends(_require_admin_token)],
)
async def shutdown() -> dict[str, str]:
    os.kill(os.getpid(), signal.SIGTERM)
    return {"message": "shutdown initiated"}
