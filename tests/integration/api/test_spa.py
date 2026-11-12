"""Caching behaviour of SPA delivery (presentation/fastapi/routers/spa.py).

`frontend/dist` is not built in the backend CI, so a minimal dist is created and
`spa.DIST_DIR` is replaced for the test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from presentation.fastapi.routers import spa


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>app</title>")
    (tmp_path / "sw.js").write_text("// service worker")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    monkeypatch.setattr(spa, "DIST_DIR", tmp_path)
    yield tmp_path


@pytest.fixture
def client(dist: Path) -> Iterator[TestClient]:
    app = FastAPI()
    assert spa.dist_available()
    app.include_router(spa.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/", "/index.html", "/sw.js", "/favicon.svg", "/members"])
def test_mutable_files_must_be_revalidated(client: TestClient, path: str) -> None:
    """Files whose content changes under the same name are revalidated with the server every time."""
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_forever(client: TestClient) -> None:
    """Content-hashed assets map one-to-one from URL to content, so they never expire."""
    response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_unchanged_file_answers_304_without_a_body(client: TestClient) -> None:
    """no-cache means "revalidate every time", not "download every time"."""
    first = client.get("/favicon.svg")
    etag = first.headers["etag"]

    second = client.get("/favicon.svg", headers={"If-None-Match": etag})

    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["etag"] == etag
    assert second.headers["cache-control"] == "no-cache"


def test_changed_file_answers_200_with_the_new_body(client: TestClient, dist: Path) -> None:
    stale_etag = client.get("/favicon.svg").headers["etag"]
    (dist / "favicon.svg").write_text("<svg><!-- redrawn --></svg>")

    response = client.get("/favicon.svg", headers={"If-None-Match": stale_etag})

    assert response.status_code == 200
    assert "redrawn" in response.text


def test_if_none_match_accepts_a_list_of_etags(client: TestClient) -> None:
    etag = client.get("/favicon.svg").headers["etag"]

    response = client.get("/favicon.svg", headers={"If-None-Match": f'"other", {etag}'})

    assert response.status_code == 304


def test_unknown_path_falls_back_to_index_html(client: TestClient) -> None:
    response = client.get("/some/spa/route")

    assert response.status_code == 200
    assert "<title>app</title>" in response.text


def test_path_traversal_falls_back_to_index_html(client: TestClient) -> None:
    response = client.get("/../../pyproject.toml")

    assert response.status_code == 200
    assert "<title>app</title>" in response.text


def test_an_unknown_api_path_is_not_swallowed(client: TestClient) -> None:
    """The fallback does not swallow `/api/` (ADR-0073 §3).

    If it did, a mistyped API would return **index.html with 200**. And since that only happens in
    production where `frontend/dist` exists, it does not reproduce locally or in tests.
    """
    response = client.get("/api/nonexistent")

    assert response.status_code == 404
    assert "<title>" not in response.text


def test_a_built_asset_under_api_is_still_served(client: TestClient, dist: Path) -> None:
    """Existing files take priority. Built assets are not refused because of `/api/`."""
    (dist / "api").mkdir()
    (dist / "api" / "config.json").write_text('{"ok": true}')

    response = client.get("/api/config.json")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_the_whole_app_still_answers_404_for_an_unknown_api_path(dist: Path, engine: sa.Engine) -> None:
    """Even with the SPA mounted on the real app, an unknown API stays 404.

    ⚠ **This is where production and local differ.** CI does not build `frontend/dist`, so a gap
    in the fallback does not reproduce in ordinary tests (only once `dist` exists).
    """
    from presentation.fastapi.app import create_app

    app = create_app()
    assert spa.dist_available()

    with TestClient(app) as client:
        response = client.get("/api/nonexistent")

    assert response.status_code == 404
    assert "<title>" not in response.text
