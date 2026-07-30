"""設定変更に伴う自己再起動 API。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_restart_status_requires_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/system/restart").status_code == 401


def test_restart_status_is_empty_before_any_request(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/system/restart", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"available_scopes": ["web"], "last_requests": []}


def test_requesting_a_restart_records_the_request(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/system/restart",
        headers=admin_headers,
        json={"reason": "log level changed"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["requested"] is True
    assert [item["scope"] for item in body["requests"]] == ["web"]
    assert body["requests"][0]["reason"] == "log level changed"
    # 要求者は PII を含まない主体識別子で記録する
    assert body["requests"][0]["requested_by"] == "user:1"

    status = client.get("/api/admin/system/restart", headers=admin_headers).json()
    assert [item["scope"] for item in status["last_requests"]] == ["web"]


def test_unknown_scope_is_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/system/restart",
        headers=admin_headers,
        json={"scopes": ["nonexistent"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_restart_scope"


def test_saving_a_startup_only_setting_reports_restart_required(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.put(
        "/api/admin/config",
        headers=admin_headers,
        json={"values": {"LOG_LEVEL": "DEBUG"}},
    )
    assert response.status_code == 200
    assert response.json()["restart_required"] == {
        "scopes": ["web"],
        "keys": ["LOG_LEVEL"],
    }


def test_saving_a_live_setting_does_not_require_a_restart(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        headers=admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.example.org"}},
    )
    assert response.status_code == 200
    assert response.json()["restart_required"] is None
