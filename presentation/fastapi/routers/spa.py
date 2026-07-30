"""SPA（frontend/dist）の配信。

ビルド済みフロントエンドが存在する場合のみマウントされる。API・docs 以外の
パスは ``index.html`` へフォールバックする（React Router の履歴モード対応）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

router = APIRouter(include_in_schema=False)


def dist_available() -> bool:
    return (DIST_DIR / "index.html").is_file()


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(DIST_DIR / "index.html")


@router.get("/{path:path}")
async def spa_fallback(path: str) -> FileResponse:
    candidate = (DIST_DIR / path).resolve()
    # パストラバーサルを防ぎつつ、実在する静的ファイルはそのまま返す
    if candidate.is_file() and candidate.is_relative_to(DIST_DIR):
        return FileResponse(candidate)
    return FileResponse(DIST_DIR / "index.html")
