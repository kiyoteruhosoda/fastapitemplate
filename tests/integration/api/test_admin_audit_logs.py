"""監査ログ（``audit_log``）の記録と閲覧 API。

「操作すると記録される」ことと「記録を絞り込める」ことの両方を見る。記録側の
テストを操作経由で書いているのは、ルーターにフックを足し忘れたら落ちてほしい
ため（リポジトリ単体では検出できない）。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from shared.domain.auth import master_data
from shared.infrastructure.models import Permission, Role, User
from shared.infrastructure.models.base import utcnow


def _search(client: TestClient, headers: dict[str, str], query: str = "") -> dict[str, Any]:
    response = client.get(f"/api/admin/audit-logs{query}", headers=headers)
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()
    return payload


def _event_types(payload: dict[str, Any]) -> list[str]:
    return [entry["event_type"] for entry in payload["entries"]]


def _insert_event(engine: sa.Engine, **overrides: object) -> None:
    session = sessionmaker(bind=engine)()
    defaults = {
        "occurred_at": utcnow(),
        "event_type": "login.succeeded",
        "result": "success",
    }
    session.add(AuditLogModel(**{**defaults, **overrides}))
    session.commit()
    session.close()


def test_audit_logs_require_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/audit-logs").status_code == 401


def test_log_view_alone_does_not_grant_audit_access(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """アプリログを見られる利用者が、そのまま監査ログを見られてはいけない。"""
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    operator_role = Role(name="log-operator")
    operator_role.permissions = list(session.scalars(sa.select(Permission).where(Permission.code == "log:view")).all())
    session.add(operator_role)
    operator = User(
        email="operator@example.com",
        username="operator",
        password_hash=generate_password_hash("operator-password"),
        is_active=True,
    )
    operator.roles = [operator_role]
    session.add(operator)
    session.commit()
    session.close()

    login = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator-password"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/admin/logs", headers=headers).status_code == 200
    assert client.get("/api/admin/audit-logs", headers=headers).status_code == 403


def test_successful_login_is_recorded(client: TestClient, admin_headers: dict[str, str]) -> None:
    payload = _search(client, admin_headers, "?event_type=login.succeeded")

    assert payload["total"] >= 1
    entry = payload["entries"][0]
    assert entry["result"] == "success"
    assert entry["actor_user_id"] == master_data.DEFAULT_ADMIN_ID
    # リクエスト単位の追跡キーが入っており、アプリログと突き合わせられる
    assert entry["request_id"]


def test_failed_login_is_recorded_against_the_account_not_the_actor(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """401 でリクエストがロールバックされても記録は残る。

    相手のアカウントは**対象**として記録する。認証に失敗した時点で「誰が試したか」は
    分かっておらず、実行者に据えると持ち主が自分でやったように読めてしまう。
    """
    response = client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401

    payload = _search(client, admin_headers, "?event_type=login.failed&result=failure")
    assert payload["total"] == 1
    entry = payload["entries"][0]
    assert entry["reason"] == "invalid_password"
    assert entry["actor_user_id"] is None
    assert (entry["target_type"], entry["target_id"]) == ("user", str(master_data.DEFAULT_ADMIN_ID))


def test_unknown_email_is_recorded_without_an_actor_or_target(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert response.status_code == 401

    entry = _search(client, admin_headers, "?event_type=login.failed")["entries"][0]
    assert entry["reason"] == "unknown_email"
    assert entry["actor_user_id"] is None
    assert entry["target_id"] is None


def test_password_reset_request_is_not_attributed_to_the_account_owner(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """未認証で叩けるので、持ち主を実行者にはしない（対象として記録する）。"""
    response = client.post("/api/auth/forgot-password", json={"email": master_data.DEFAULT_ADMIN_EMAIL})
    assert response.status_code == 200

    entry = _search(client, admin_headers, "?event_type=password_reset.requested")["entries"][0]
    assert entry["actor_user_id"] is None
    assert (entry["target_type"], entry["target_id"]) == ("user", str(master_data.DEFAULT_ADMIN_ID))


def test_user_management_records_the_actor_and_the_target(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/admin/users",
        json={"email": "audited@example.com", "username": "audited", "password": "password123", "roles": []},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    updated = client.put(f"/api/admin/users/{user_id}", json={"is_active": False}, headers=admin_headers)
    assert updated.status_code == 200

    payload = _search(client, admin_headers, "?target_type=user")
    assert _event_types(payload) == ["user.updated", "user.created"]
    assert {entry["target_id"] for entry in payload["entries"]} == {str(user_id)}
    assert {entry["actor_user_id"] for entry in payload["entries"]} == {master_data.DEFAULT_ADMIN_ID}
    # 変更した項目名だけを残す（値そのものは残さない）
    assert payload["entries"][0]["reason"] == "fields=is_active"


def test_password_change_does_not_record_the_password(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": master_data.DEFAULT_ADMIN_PASSWORD, "new_password": "another-password"},
        headers=admin_headers,
    )
    assert response.status_code == 200

    entry = _search(client, admin_headers, "?event_type=password.changed")["entries"][0]
    assert entry["result"] == "success"
    assert entry["reason"] is None


def test_settings_update_records_only_the_changed_keys(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/admin/config",
        json={"values": {"LOG_DB_MIN_LEVEL": "WARNING"}},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    entry = _search(client, admin_headers, "?event_type=system_settings.updated")["entries"][0]
    assert entry["reason"] == "keys=LOG_DB_MIN_LEVEL"
    assert entry["target_type"] == "system_settings"


def test_filters_by_actor_and_request_id(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    _insert_event(engine, actor_user_id=999, request_id="req-audit")

    by_actor = _search(client, admin_headers, "?actor_user_id=999")
    assert by_actor["total"] == 1
    assert by_actor["entries"][0]["request_id"] == "req-audit"

    assert _search(client, admin_headers, "?request_id=req-audit")["total"] == 1
    assert _search(client, admin_headers, "?request_id=nothing")["total"] == 0


def test_paginates_newest_first(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    now = utcnow()
    for index in range(3):
        _insert_event(
            engine,
            occurred_at=now + timedelta(seconds=index),
            event_type="role.updated",
            target_id=str(index),
        )

    first = _search(client, admin_headers, "?event_type=role.updated&limit=2")
    assert [entry["target_id"] for entry in first["entries"]] == ["2", "1"]
    assert first["total"] == 3

    second = _search(client, admin_headers, "?event_type=role.updated&limit=2&offset=2")
    assert [entry["target_id"] for entry in second["entries"]] == ["0"]


def test_filter_options_expose_the_known_event_types(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/audit-logs/filters", headers=admin_headers)
    assert response.status_code == 200

    options = response.json()
    assert "login.succeeded" in options["event_types"]
    assert options["results"] == ["success", "failure"]
    assert "user" in options["target_types"]
