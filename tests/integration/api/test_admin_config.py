import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from shared.infrastructure.models import SystemSetting
from shared.kernel.settings.settings import settings


def test_config_requires_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/config").status_code == 401


def test_get_config_returns_definitions(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/config", headers=system_admin_headers)
    assert response.status_code == 200
    items = {item["key"]: item for item in response.json()}
    assert "MAIL_SERVER" in items
    assert items["MAIL_SERVER"]["env_fallback"] is False
    # secret items do not return the value as is
    assert items["MAIL_PASSWORD"]["value"] in (None, "", "********")


def test_save_config_overrides_default(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        headers=system_admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.custom.example"}},
    )
    assert response.status_code == 200

    # Takes effect immediately through the settings object (DB > environment variable > default)
    assert settings.mail_server == "smtp.custom.example"

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    assert items["MAIL_SERVER"]["value"] == "smtp.custom.example"
    assert items["MAIL_SERVER"]["stored"] is True

    # null deletes the DB override and returns to the default
    client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": None}})
    assert settings.mail_server == "smtp.example.com"


def test_unknown_key_is_ignored(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        headers=system_admin_headers,
        json={"values": {"DATABASE_URI": "sqlite:///evil.db"}},
    )
    assert response.status_code == 200
    items = {i["key"] for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    assert "DATABASE_URI" not in items


def test_saved_value_wins_over_environment(
    client: TestClient, system_admin_headers: dict[str, str], monkeypatch: MonkeyPatch
) -> None:
    """⚠ **A value saved on screen beats the environment variable.**

    Otherwise, a key written as one line in compose would be **shown on screen but impossible to change**.
    """
    monkeypatch.setenv("MAIL_SERVER", "smtp.from-env.example")
    settings.reload_db_overrides()
    # Without a saved value the environment variable applies (= it still works as the deployment initial value)
    assert settings.mail_server == "smtp.from-env.example"

    client.put(
        "/api/admin/config",
        headers=system_admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.from-screen.example"}},
    )
    assert settings.mail_server == "smtp.from-screen.example"

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    # ⚠ Not a lock marker: it tells you "deleting it falls back to the environment variable"
    assert items["MAIL_SERVER"]["env_fallback"] is True
    assert items["MAIL_SERVER"]["value"] == "smtp.from-screen.example"

    # Deleting it falls back to the environment variable (not the default)
    client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": None}})
    assert settings.mail_server == "smtp.from-env.example"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("anything", False),
        ("true", True),
        (" True ", True),
        ("1", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_boolean_from_environment_is_shown_as_the_server_reads_it(
    client: TestClient, system_admin_headers: dict[str, str], monkeypatch: MonkeyPatch, raw: str, expected: bool
) -> None:
    """Returning the environment variable ``"false"`` as a string would show as on in the screen (task #828)."""
    monkeypatch.setenv("SESSION_COOKIE_SECURE", raw)
    settings.reload_db_overrides()

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}

    assert items["SESSION_COOKIE_SECURE"]["value"] is expected
    assert settings.session_cookie_secure is expected
    assert items["SESSION_COOKIE_SECURE"]["env_fallback"] is True


def test_saved_boolean_wins_over_environment_string(
    client: TestClient, system_admin_headers: dict[str, str], monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    settings.reload_db_overrides()

    client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"SESSION_COOKIE_SECURE": True}})

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    assert items["SESSION_COOKIE_SECURE"]["value"] is True


def test_env_only_setting_cannot_be_saved_from_the_screen(
    client: TestClient, system_admin_headers: dict[str, str], monkeypatch: MonkeyPatch
) -> None:
    """Destinations and key locations are set only by environment variables and shown read-only on screen (ADR-0090)."""
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.from-env.example")
    for key, value in (
        ("OIDC_ISSUER", "https://attacker.example"),
        ("OIDC_PRIVATE_KEY_FILE", "/etc/passwd"),
        ("FCM_SERVICE_ACCOUNT_FILE", "/etc/passwd"),
        ("WEB_PUSH_VAPID_PRIVATE_KEY_FILE", "/etc/passwd"),
        ("APP_RELEASE_S3_ENDPOINT_URL", "http://10.10.2.11:11000"),
        ("APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE", "/etc/passwd"),
    ):
        response = client.put("/api/admin/config", headers=system_admin_headers, json={"values": {key: value}})
        assert response.status_code == 400, key
        assert response.json()["detail"] == {"error": "setting_env_only", "key": key}

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    assert items["OIDC_ISSUER"]["env_only"] is True
    assert items["OIDC_ISSUER"]["value"] == "https://idp.from-env.example"
    assert items["MAIL_SERVER"]["env_only"] is False


def test_env_only_setting_ignores_a_value_left_in_the_database(db_session: Session, monkeypatch: MonkeyPatch) -> None:
    """Values entered on screen before the import are not read even if they remain in the DB."""
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.from-env.example")
    db_session.add(
        SystemSetting(
            setting_key="app.config",
            setting_json={"OIDC_ISSUER": "https://left.example", "MAIL_SERVER": "smtp.left.example"},
        )
    )
    db_session.commit()
    settings.reload_db_overrides()

    assert settings.oidc_issuer == "https://idp.from-env.example"
    assert settings.mail_server == "smtp.left.example"


def test_mail_server_inside_the_home_is_refused(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    for host in ("10.10.2.11", "127.0.0.1", "db", "db.ns.svc.cluster.local", "smtp.local", "https://smtp.example.com"):
        response = client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": host}})
        assert response.status_code == 400, host
        assert response.json()["detail"] == {"error": "invalid_destination", "key": "MAIL_SERVER"}

    # Clearing it is allowed
    assert (
        client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": ""}}).status_code
        == 200
    )
    client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": None}})
