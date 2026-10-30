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
    # secret 項目は値をそのまま返さない
    assert items["MAIL_PASSWORD"]["value"] in (None, "", "********")


def test_save_config_overrides_default(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        headers=system_admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.custom.example"}},
    )
    assert response.status_code == 200

    # settings オブジェクト経由で即時反映される（DB > 環境変数 > デフォルト）
    assert settings.mail_server == "smtp.custom.example"

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    assert items["MAIL_SERVER"]["value"] == "smtp.custom.example"
    assert items["MAIL_SERVER"]["stored"] is True

    # null で DB 上書きを削除しデフォルトへ戻す
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
    """⚠ **画面で保存した値は環境変数より強い。**

    逆にすると、compose に 1 行書いた鍵は**画面に出ているのに変えられない**。
    """
    monkeypatch.setenv("MAIL_SERVER", "smtp.from-env.example")
    settings.reload_db_overrides()
    # 保存が無ければ環境変数が効く（＝配るときの初期値としては生きている）
    assert settings.mail_server == "smtp.from-env.example"

    client.put(
        "/api/admin/config",
        headers=system_admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.from-screen.example"}},
    )
    assert settings.mail_server == "smtp.from-screen.example"

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=system_admin_headers).json()}
    # ⚠ 止める印ではない ——「消すと環境変数へ戻る」という案内である
    assert items["MAIL_SERVER"]["env_fallback"] is True
    assert items["MAIL_SERVER"]["value"] == "smtp.from-screen.example"

    # 消せば環境変数へ戻る（デフォルトではない）
    client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": None}})
    assert settings.mail_server == "smtp.from-env.example"


def test_env_only_setting_cannot_be_saved_from_the_screen(
    client: TestClient, system_admin_headers: dict[str, str], monkeypatch: MonkeyPatch
) -> None:
    """通信先と鍵の場所は環境変数だけで決め、画面には見るだけで出す（ADR-0090）。"""
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
    """取り込む前に画面で入れた値が DB に残っていても読まない。"""
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

    # 空に戻す操作は通る
    assert (
        client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": ""}}).status_code
        == 200
    )
    client.put("/api/admin/config", headers=system_admin_headers, json={"values": {"MAIL_SERVER": None}})
