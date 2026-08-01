"""システムステータス API（要 ``system:manage``）。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _member_headers(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    """``system:manage`` を持たないユーザーのトークンを用意する。"""
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "member@example.com", "username": "member", "password": "password-123", "roles": ["member"]},
    )
    assert created.status_code == 201, created.text
    login = client.post("/api/auth/login", json={"email": "member@example.com", "password": "password-123"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_status_requires_authentication(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/system/status").status_code == 401


def test_status_requires_system_manage(client: TestClient, admin_headers: dict[str, str]) -> None:
    headers = _member_headers(client, admin_headers)
    client.cookies.clear()
    response = client.get("/api/admin/system/status", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "forbidden"


def test_status_reports_build_info_and_component_health(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/system/status", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["version"]
    assert data["git_sha"]
    assert data["components"] == {"api": "ok", "database": "ok"}
    assert data["uptime_seconds"] >= 0
    assert data["timestamp_utc"]
