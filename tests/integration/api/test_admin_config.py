from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from shared.kernel.settings.settings import settings


def test_config_requires_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/config").status_code == 401


def test_get_config_returns_definitions(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/config", headers=admin_headers)
    assert response.status_code == 200
    items = {item["key"]: item for item in response.json()}
    assert "MAIL_SERVER" in items
    assert items["MAIL_SERVER"]["env_fallback"] is False
    # secret 項目は値をそのまま返さない
    assert items["MAIL_PASSWORD"]["value"] in (None, "", "********")


def test_save_config_overrides_default(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        headers=admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.custom.example"}},
    )
    assert response.status_code == 200

    # settings オブジェクト経由で即時反映される（DB > 環境変数 > デフォルト）
    assert settings.mail_server == "smtp.custom.example"

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=admin_headers).json()}
    assert items["MAIL_SERVER"]["value"] == "smtp.custom.example"
    assert items["MAIL_SERVER"]["stored"] is True

    # null で DB 上書きを削除しデフォルトへ戻す
    client.put("/api/admin/config", headers=admin_headers, json={"values": {"MAIL_SERVER": None}})
    assert settings.mail_server == "smtp.example.com"


def test_unknown_key_is_ignored(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        headers=admin_headers,
        json={"values": {"DATABASE_URI": "sqlite:///evil.db"}},
    )
    assert response.status_code == 200
    items = {i["key"] for i in client.get("/api/admin/config", headers=admin_headers).json()}
    assert "DATABASE_URI" not in items


def test_saved_value_wins_over_environment(
    client: TestClient, admin_headers: dict[str, str], monkeypatch: MonkeyPatch
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
        headers=admin_headers,
        json={"values": {"MAIL_SERVER": "smtp.from-screen.example"}},
    )
    assert settings.mail_server == "smtp.from-screen.example"

    items = {i["key"]: i for i in client.get("/api/admin/config", headers=admin_headers).json()}
    # ⚠ 止める印ではない ——「消すと環境変数へ戻る」という案内である
    assert items["MAIL_SERVER"]["env_fallback"] is True
    assert items["MAIL_SERVER"]["value"] == "smtp.from-screen.example"

    # 消せば環境変数へ戻る（デフォルトではない）
    client.put("/api/admin/config", headers=admin_headers, json={"values": {"MAIL_SERVER": None}})
    assert settings.mail_server == "smtp.from-env.example"
