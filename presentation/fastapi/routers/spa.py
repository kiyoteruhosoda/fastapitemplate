"""Serving the SPA (frontend/dist).

Mounted only when a built frontend exists. Paths other than the API and docs fall back to
``index.html`` (for React Router's history mode).

⚠ **Paths under ``/api/`` never fall through to the catch-all** (ADR-0073 §3). This router is a
catch-all, so without care **a nonexistent API path returns index.html with 200**. And since that
only happens when `frontend/dist` exists, **it occurs only in production and cannot be
reproduced locally or in tests**. A mistyped API path returns 404 whether or not dist exists.

Two kinds of files are served, with different caching.

- Under ``assets/``: Vite writes them with content-hashed names. When content changes the URL
  changes too, so they can be cached without expiry.
- Everything else (``index.html``, ``sw.js``, ``manifest.webmanifest``, icons): content changes
  under the same name. Without ``no-cache`` (= revalidate every time), devices keep the old
  version and neither the UI nor icons change after a deploy.

``no-cache`` means "revalidate every time", not "download every time". If the ``ETag`` matches,
304 is returned without a body (``FileResponse`` sets ``ETag`` but ignores conditional requests,
so this is decided here).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

INDEX_HTML = "index.html"

#: Paths that never fall through to the catch-all. A match returns 404.
#: **The response has the same shape as without dist** (FastAPI's default 404), so callers
#: see the same behaviour whether or not the frontend is baked in.
API_PREFIX = "api/"
HASHED_ASSETS_PREFIX = "assets/"
CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "no-cache"

# Headers that must be sent even with 304 (RFC 9110 §15.4.5).
_NOT_MODIFIED_HEADERS = ("etag", "cache-control", "last-modified", "vary")

router = APIRouter(include_in_schema=False)


def dist_available() -> bool:
    return (DIST_DIR / INDEX_HTML).is_file()


def _cache_control(relative_path: str) -> str:
    if relative_path.startswith(HASHED_ASSETS_PREFIX):
        return CACHE_IMMUTABLE
    return CACHE_REVALIDATE


def _matches_etag(request: Request, etag: str | None) -> bool:
    """Whether ``If-None-Match`` contains our ``ETag``."""
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
    # Passing stat_result fixes ETag / Last-Modified at construction (otherwise they are not
    # set until just before the body is sent, and conditional requests can't be decided here).
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
    # Return existing static files as is while preventing path traversal
    if candidate.is_file() and candidate.is_relative_to(DIST_DIR):
        return _serve(candidate, path, request)
    if path.startswith(API_PREFIX):
        # Nonexistent API. **Never return index.html** (the caller expects JSON).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _serve(DIST_DIR / INDEX_HTML, INDEX_HTML, request)
