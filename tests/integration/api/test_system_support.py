"""サポート担当（テナントの外で、状態を見るだけ。ADR-0084 §2・§4）。

運用者が「テナントの外の人」としてロールを選んで足す。サポート担当はテナントの一覧と
システムの状態を見られるが、設定・アプリログ・監査ログ・人の付け外しには入れず、何も変えられない。
最後の運用者を外す関門は、サポート担当を運用者として数えない。
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from shared.infrastructure.models import User
from shared.infrastructure.tenant_registry import count_active_system_administrators
from tests.conftest import sign_in

_SUPPORT_EMAIL = "help@ops.example"
_SUPPORT_PASSWORD = "support-password-1"


def _add_support(client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine) -> int:
    added = client.post(
        "/api/system/administrators",
        json={"email": _SUPPORT_EMAIL, "username": "help", "role": "system-support"},
        headers=system_admin_headers,
    )
    assert added.status_code == 201, added.text
    user_id = int(added.json()["user_id"])
    # 招待のメールの代わりに、試験ではパスワードを直に置く
    with Session(engine) as session:
        user = session.get(User, user_id)
        assert user is not None
        user.password_hash = generate_password_hash(_SUPPORT_PASSWORD)
        session.commit()
    return user_id


def test_support_is_listed_with_its_role(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    user_id = _add_support(client, system_admin_headers, engine)
    roles = {a["id"]: a["role"] for a in client.get("/api/system/administrators").json()}
    assert roles[user_id] == "system-support"
    assert "system-admin" in roles.values()


def test_support_looks_but_does_not_touch(
    client: TestClient, other_client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    _add_support(client, system_admin_headers, engine)
    headers = sign_in(other_client, _SUPPORT_EMAIL, _SUPPORT_PASSWORD)

    assert other_client.get("/api/system/tenants").status_code == 200
    assert other_client.get("/api/admin/system/status").status_code == 200

    refused = {
        "registers a tenant": other_client.post(
            "/api/system/tenants",
            json={"slug": "acme", "display_name": "Acme", "first_admin": {"email": "b@acme.example", "username": "b"}},
            headers=headers,
        ),
        "reads system settings": other_client.get("/api/admin/config"),
        "changes system settings": other_client.put(
            "/api/admin/config", json={"values": {"MAIL_SERVER": "x"}}, headers=headers
        ),
        "restarts": other_client.post("/api/admin/system/restart", json={}, headers=headers),
        "reads app logs": other_client.get("/api/admin/logs"),
        "reads audit logs": other_client.get("/api/admin/audit-logs"),
        "lists operators": other_client.get("/api/system/administrators"),
    }
    assert {what: r.status_code for what, r in refused.items()} == dict.fromkeys(refused, 403)


def test_support_is_not_counted_as_an_operator(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    with Session(engine) as session:
        before = count_active_system_administrators(session)
    _add_support(client, system_admin_headers, engine)
    with Session(engine) as session:
        assert count_active_system_administrators(session) == before


def test_an_unknown_role_is_refused(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    refused = client.post(
        "/api/system/administrators",
        json={"email": "x@ops.example", "username": "x", "role": "owner"},
        headers=system_admin_headers,
    )
    assert refused.status_code == 422
