"""SPA（frontend/dist）の配信。

ビルド済みフロントエンドが存在する場合のみマウントされる。API・docs 以外の
パスは ``index.html`` へフォールバックする（React Router の履歴モード対応）。

配信するファイルは 2 種類あり、キャッシュの扱いを分ける。

- ``assets/`` 配下: Vite が内容ハッシュ付きの名前で書き出す。中身が変われば
  URL も変わるので、期限を切らずに持たせてよい。
- それ以外（``index.html``・``sw.js``・``manifest.webmanifest``・アイコン）:
  名前が変わらないまま中身が変わる。``no-cache``（＝毎回問い合わせる）を付けないと
  端末が古い版を持ち続け、デプロイしても画面もアイコンも変わらない。

``no-cache`` は「毎回問い合わせる」であって「毎回落とす」ではない。``ETag`` が
一致すれば本文を省いて 304 を返す（``FileResponse`` は ``ETag`` を付けるが
条件付きリクエストは見ないため、ここで判定する）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response

DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

INDEX_HTML = "index.html"
HASHED_ASSETS_PREFIX = "assets/"
CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "no-cache"

# 304 でも返す必要のあるヘッダー（RFC 9110 §15.4.5）。
_NOT_MODIFIED_HEADERS = ("etag", "cache-control", "last-modified", "vary")

router = APIRouter(include_in_schema=False)


def dist_available() -> bool:
    return (DIST_DIR / INDEX_HTML).is_file()


def _cache_control(relative_path: str) -> str:
    if relative_path.startswith(HASHED_ASSETS_PREFIX):
        return CACHE_IMMUTABLE
    return CACHE_REVALIDATE


def _matches_etag(request: Request, etag: str | None) -> bool:
    """``If-None-Match`` に手持ちの ``ETag`` が含まれているか。"""
    if etag is None:
        return False
    header = request.headers.get("if-none-match")
    if header is None:
        return False
    if header.strip() == "*":
        return True
    return any(candidate.strip() == etag for candidate in header.split(","))


def _not_modified(response: FileResponse) -> Response:
    headers = {name: response.headers[name] for name in _NOT_MODIFIED_HEADERS if name in response.headers}
    return Response(status_code=304, headers=headers)


def _serve(file_path: Path, relative_path: str, request: Request) -> Response:
    # stat_result を渡すと ETag / Last-Modified が生成時に決まる（省くと本文送信の
    # 直前まで決まらず、ここで条件付きリクエストを判定できない）。
    response = FileResponse(
        file_path,
        headers={"cache-control": _cache_control(relative_path)},
        stat_result=file_path.stat(),
    )
    if _matches_etag(request, response.headers.get("etag")):
        return _not_modified(response)
    return response


@router.get("/")
async def index(request: Request) -> Response:
    return _serve(DIST_DIR / INDEX_HTML, INDEX_HTML, request)


@router.get("/{path:path}")
async def spa_fallback(path: str, request: Request) -> Response:
    candidate = (DIST_DIR / path).resolve()
    # パストラバーサルを防ぎつつ、実在する静的ファイルはそのまま返す
    if candidate.is_file() and candidate.is_relative_to(DIST_DIR):
        return _serve(candidate, path, request)
    return _serve(DIST_DIR / INDEX_HTML, INDEX_HTML, request)
