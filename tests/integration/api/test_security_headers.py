"""全部の応答に守りのヘッダが付く（ADR-0073 §5）。

前段の nginx に頼らず、アプリ自身が付ける。雛形から起こしたアプリには必ず入る。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from presentation.fastapi.middleware.csrf import CSRF_COOKIE
from presentation.fastapi.routers import spa
from shared.domain.auth import master_data


def _assert_guarded(headers: Mapping[str, str]) -> None:
    csp = headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("referrer-policy") == "no-referrer"


@pytest.fixture
def page_client(engine: sa.Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """画面（SPA）も配るアプリ。CI の Backend では dist を焼かないので最小のものを置く。"""
    from presentation.fastapi.app import create_app

    (tmp_path / "index.html").write_text("<!doctype html><title>app</title>")
    monkeypatch.setattr(spa, "DIST_DIR", tmp_path)
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/login", "/admin/users"])
def test_pages_carry_the_headers(page_client: TestClient, path: str) -> None:
    response = page_client.get(path)
    assert response.status_code == 200
    _assert_guarded(response.headers)


@pytest.mark.parametrize("path", ["/api/health", "/api/auth/me", "/api/admin/users"])
def test_api_responses_carry_the_headers_even_when_refused(client: TestClient, path: str) -> None:
    client.cookies.clear()
    _assert_guarded(client.get(path).headers)


def test_a_request_refused_by_csrf_carries_the_headers(client: TestClient) -> None:
    client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert client.cookies[CSRF_COOKIE]
    refused = client.post("/api/auth/switch-role", json={"role": None})
    assert refused.status_code == 403
    _assert_guarded(refused.headers)


def test_the_api_documentation_reads_its_cdn(client: TestClient) -> None:
    """``/docs`` は外の CDN からスクリプトを読むので、CSP だけ付けない。"""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-frame-options"] == "DENY"


def test_hsts_only_when_served_over_https(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    assert "strict-transport-security" not in client.get("/api/health").headers

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    assert client.get("/api/health").headers["strict-transport-security"] == "max-age=31536000"
