"""アクティブロールの切り替え（ADR-0017）。

複数ロールを持つユーザーが、いま使うロールを 1 つに絞れること・戻せること、
そして絞ったあいだは他のロールの権限で操作できないことを確認する。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from shared.infrastructure.models import User
from tests.conftest import sign_in

_EMAIL = "multi-role@example.com"
_PASSWORD = "password-123"


def _create_multi_role_user(client: TestClient, admin_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": _EMAIL,
            "username": "multi",
            "password": _PASSWORD,
            "roles": ["manager", "member"],
        },
    )
    assert created.status_code == 201, created.text


def _sign_in(client: TestClient) -> dict[str, str]:
    return sign_in(client, _EMAIL, _PASSWORD)


def _switch(client: TestClient, headers: dict[str, str], role: str | None) -> tuple[int, dict[str, str]]:
    """切り替えて、成功したら新しいセッションのヘッダーを返す。

    トークンは Cookie に載り替わる（ADR-0028）。CSRF トークンも新しくなるので
    読み直す。
    """
    response = client.post("/api/auth/switch-role", headers=headers, json={"role": role})
    if response.status_code != 200:
        return response.status_code, headers
    return 200, {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def test_me_lists_every_granted_role(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    me = client.get("/api/auth/me", headers=_sign_in(client)).json()

    assert me["roles"] == ["manager", "member"]
    # 既定は「すべてのロール」= 保有権限の和集合
    assert me["active_role"] is None
    assert "log:view" in me["scopes"]


def test_switching_narrows_the_effective_scopes(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    status_code, headers = _switch(client, _sign_in(client), "member")
    assert status_code == 200

    me = client.get("/api/auth/me", headers=headers).json()
    assert me["active_role"] == "member"
    # member が持つのは dashboard:view / gui:view / item:view だけ
    assert me["scopes"] == ["dashboard:view", "gui:view", "item:view"]
    # 絞り込んだあいだは manager 側の権限では通らない
    assert client.get("/api/admin/logs", headers=headers).status_code == 403


def test_switching_back_restores_the_union(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    _, narrowed = _switch(client, _sign_in(client), "member")
    status_code, restored = _switch(client, narrowed, None)
    assert status_code == 200

    me = client.get("/api/auth/me", headers=restored).json()
    assert me["active_role"] is None
    assert "log:view" in me["scopes"]


def test_cannot_switch_to_a_role_not_granted(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    response = client.post("/api/auth/switch-role", headers=_sign_in(client), json={"role": "admin"})

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "role_not_granted"


def test_unknown_role_is_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    response = client.post("/api/auth/switch-role", headers=_sign_in(client), json={"role": "no-such-role"})

    assert response.status_code == 403


def test_refresh_keeps_the_active_role(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    _, headers = _switch(client, _sign_in(client), "member")

    refreshed = client.post("/api/auth/refresh", headers=headers)
    assert refreshed.status_code == 200

    # 更新でセッションが載せ替わっても、アクティブロールは引き継がれる（ADR-0017）。
    me = client.get("/api/auth/me").json()
    assert me["active_role"] == "member"


def test_revoking_the_active_role_drops_its_scopes(
    client: TestClient,
    other_client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    """切り替えた後にロールを外されたら、そのトークンの権限は残らない。"""
    _create_multi_role_user(client, admin_headers)
    # Cookie でセッションを持つので、利用者ごとにクライアントを分ける（ADR-0028）。
    _switch(other_client, _sign_in(other_client), "member")

    user = db_session.scalar(select(User).where(User.email == _EMAIL))
    assert user is not None
    updated = client.put(
        f"/api/admin/users/{user.id}",
        headers=admin_headers,
        json={"roles": ["manager"]},
    )
    assert updated.status_code == 200

    me = other_client.get("/api/auth/me").json()
    assert me["scopes"] == []
    assert me["roles"] == ["manager"]


def test_switch_is_audited(client: TestClient, other_client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_multi_role_user(client, admin_headers)
    _switch(other_client, _sign_in(other_client), "member")

    entries = client.get("/api/admin/audit-logs", headers=admin_headers, params={"event_type": "role.switched"}).json()
    assert entries["total"] == 1
    assert entries["entries"][0]["reason"] == "role=member"
    assert entries["entries"][0]["result"] == "success"
