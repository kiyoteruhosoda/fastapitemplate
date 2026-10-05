"""管理 API の「権限を動かす操作」の関門（ADR-0051）。

scope を持っていても、自分の権限を超えて配る・格上に触れる・自分を変える・
最後の管理者を失う、の 4 つは通らない。
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from shared.domain.auth import master_data
from tests.conftest import sign_in

_PASSWORD = "password-123"


def _add_user(client: TestClient, headers: dict[str, str], name: str, roles: list[str]) -> int:
    response = client.post(
        "/api/admin/users",
        headers=headers,
        json={"email": f"{name}@example.com", "username": name, "password": _PASSWORD, "roles": roles},
    )
    assert response.status_code == 201, response.text
    user_id: int = response.json()["id"]
    return user_id


def _error(body: Any) -> str:
    return str(body["detail"]["error"])


def _admin_id(client: TestClient, headers: dict[str, str]) -> int:
    users = client.get("/api/admin/users", headers=headers).json()
    return int(next(u["id"] for u in users if u["email"] == master_data.DEFAULT_ADMIN_EMAIL))


# --- 自分の権限を超えて配らない -------------------------------------------


def test_user_admin_can_onboard_a_member(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _add_user(client, admin_headers, "helpdesk", ["user-admin"])
    headers = sign_in(other_client, "helpdesk@example.com", _PASSWORD)

    response = other_client.post(
        "/api/admin/users",
        headers=headers,
        json={"email": "new@example.com", "username": "new", "password": _PASSWORD, "roles": ["member"]},
    )

    assert response.status_code == 201, response.text


def test_user_admin_cannot_grant_a_stronger_role(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    member_id = _add_user(client, admin_headers, "someone", ["member"])
    helpdesk_id = _add_user(client, admin_headers, "helpdesk", ["user-admin"])
    headers = sign_in(other_client, "helpdesk@example.com", _PASSWORD)

    created = other_client.post(
        "/api/admin/users",
        headers=headers,
        json={"email": "boss@example.com", "username": "boss", "password": _PASSWORD, "roles": ["admin"]},
    )
    raised = other_client.put(f"/api/admin/users/{member_id}", headers=headers, json={"roles": ["manager"]})
    self_raised = other_client.put(f"/api/admin/users/{helpdesk_id}", headers=headers, json={"roles": ["admin"]})

    assert created.status_code == 403
    assert _error(created.json()) == "beyond_your_permissions"
    assert "role:manage" in created.json()["detail"]["permissions"]
    assert raised.status_code == 403
    assert _error(raised.json()) == "beyond_your_permissions"
    assert self_raised.status_code == 403


def test_user_admin_cannot_touch_a_stronger_user(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """格上のパスワードを書き換えれば、その人の権限を丸ごと取れてしまう。"""
    admin_id = _admin_id(client, admin_headers)
    _add_user(client, admin_headers, "helpdesk", ["user-admin"])
    headers = sign_in(other_client, "helpdesk@example.com", _PASSWORD)

    password = other_client.put(f"/api/admin/users/{admin_id}", headers=headers, json={"password": "taken-over-1"})
    removed = other_client.delete(f"/api/admin/users/{admin_id}", headers=headers)

    assert password.status_code == 403
    assert _error(password.json()) == "beyond_your_permissions"
    assert removed.status_code == 403


def test_role_keeper_cannot_put_codes_they_lack_into_a_role(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/admin/roles",
        headers=admin_headers,
        json={"name": "role-keeper", "permissions": ["role:manage", "dashboard:view"]},
    )
    assert created.status_code == 201, created.text
    _add_user(client, admin_headers, "keeper", ["role-keeper"])
    headers = sign_in(other_client, "keeper@example.com", _PASSWORD)
    admin_role_id = next(
        r["id"] for r in client.get("/api/admin/roles", headers=admin_headers).json() if r["name"] == "admin"
    )

    escalated = other_client.post(
        "/api/admin/roles", headers=headers, json={"name": "mine", "permissions": ["user:manage"]}
    )
    stripped = other_client.put(f"/api/admin/roles/{admin_role_id}", headers=headers, json={"permissions": []})
    within = other_client.post(
        "/api/admin/roles", headers=headers, json={"name": "viewer", "permissions": ["dashboard:view"]}
    )

    assert escalated.status_code == 403
    assert _error(escalated.json()) == "beyond_your_permissions"
    assert stripped.status_code == 403
    assert within.status_code == 201, within.text


# --- 自分自身は変えない ------------------------------------------------------


def test_an_admin_cannot_change_their_own_standing(client: TestClient, admin_headers: dict[str, str]) -> None:
    admin_id = _admin_id(client, admin_headers)

    for response in (
        client.put(f"/api/admin/users/{admin_id}", headers=admin_headers, json={"roles": ["member"]}),
        client.put(f"/api/admin/users/{admin_id}", headers=admin_headers, json={"is_active": False}),
        client.delete(f"/api/admin/users/{admin_id}", headers=admin_headers),
    ):
        assert response.status_code == 403
        assert _error(response.json()) == "cannot_change_yourself"


def test_an_admin_can_still_rename_themselves(client: TestClient, admin_headers: dict[str, str]) -> None:
    """止めるのはロール・有効状態・削除だけ。同じロールを送り直すのも変更ではない。"""
    admin_id = _admin_id(client, admin_headers)

    response = client.put(
        f"/api/admin/users/{admin_id}",
        headers=admin_headers,
        json={"username": "owner", "roles": ["admin"]},
    )

    assert response.status_code == 200, response.text


# --- 最後の管理者を失わない --------------------------------------------------


def test_the_last_administrator_role_cannot_be_hollowed_out(client: TestClient, admin_headers: dict[str, str]) -> None:
    roles = client.get("/api/admin/roles", headers=admin_headers).json()
    admin_role = next(r for r in roles if r["name"] == "admin")
    without_core = [code for code in admin_role["permissions"] if code != "role:manage"]

    hollowed = client.put(
        f"/api/admin/roles/{admin_role['id']}", headers=admin_headers, json={"permissions": without_core}
    )
    deleted = client.delete(f"/api/admin/roles/{admin_role['id']}", headers=admin_headers)

    assert hollowed.status_code == 409
    assert _error(hollowed.json()) == "last_administrator"
    assert deleted.status_code == 409
    after = next(r for r in client.get("/api/admin/roles", headers=admin_headers).json() if r["name"] == "admin")
    assert "role:manage" in after["permissions"]


def test_a_stale_token_cannot_disable_the_last_administrator(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """ロールを外されても、手元のアクセストークンは寿命まで通る（ADR-0041）。

    その古い 1 枚で残った 1 人を止めると、誰も権限を配り直せなくなる。
    """
    admin_id = _admin_id(client, admin_headers)
    second_id = _add_user(client, admin_headers, "second", ["admin"])
    second_headers = sign_in(other_client, "second@example.com", _PASSWORD)

    # second が既定の管理者から admin を外す（有効な管理者は second だけになる）
    demoted = other_client.put(f"/api/admin/users/{admin_id}", headers=second_headers, json={"roles": ["member"]})
    assert demoted.status_code == 200, demoted.text

    # 既定の管理者は古いトークンのまま、最後の 1 人を止めようとする
    response = client.put(f"/api/admin/users/{second_id}", headers=admin_headers, json={"is_active": False})

    assert response.status_code == 409
    assert _error(response.json()) == "last_administrator"
    users = other_client.get("/api/admin/users").json()
    assert next(u for u in users if u["id"] == second_id)["is_active"] is True
