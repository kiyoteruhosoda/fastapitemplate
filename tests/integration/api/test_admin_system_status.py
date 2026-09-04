"""システムステータス API（要 ``system:manage``）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import sign_in


def _sign_in_member(client: TestClient, member_client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    """``system:manage`` を持たない利用者で**別のクライアント**にログインする。

    セッションは Cookie で持つので（ADR-0028）、管理者と同じクライアントで
    ログインすると管理者のセッションが置き換わってしまう。
    """
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "member@example.com", "username": "member", "password": "password-123", "roles": ["member"]},
    )
    assert created.status_code == 201, created.text
    return sign_in(member_client, "member@example.com", "password-123")


def test_status_requires_authentication(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/system/status").status_code == 401


def test_status_requires_system_manage(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _sign_in_member(client, other_client, admin_headers)
    response = other_client.get("/api/admin/system/status")
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
