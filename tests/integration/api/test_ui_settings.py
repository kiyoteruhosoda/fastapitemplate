"""画面の初期設定 API（未認証で読める）。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_ui_settings_are_public(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/api/ui/settings")
    assert response.status_code == 200
    assert response.json() == {
        "languages": ["en", "ja"],
        "default_locale": "en",
        "default_theme": "system",
    }


def test_ui_settings_follow_the_admin_configuration(client: TestClient, admin_headers: dict[str, str]) -> None:
    client.put(
        "/api/admin/config",
        headers=admin_headers,
        json={"values": {"DEFAULT_LOCALE": "ja", "DEFAULT_THEME": "dark"}},
    )
    body = client.get("/api/ui/settings").json()
    assert body["default_locale"] == "ja"
    assert body["default_theme"] == "dark"
