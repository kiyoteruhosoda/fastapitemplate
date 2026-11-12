"""The gate on "operations that move permissions" in the admin API (ADR-0078 §4).

Even with the scope, four things never pass: granting beyond your own permissions, touching a
higher-ranked user, changing yourself, and losing the last administrator.
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


# --- Do not grant beyond your own permissions -------------------------------------


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
        json={"email": "boss@example.com", "username": "boss", "password": _PASSWORD, "roles": ["owner"]},
    )
    raised = other_client.put(f"/api/admin/users/{member_id}", headers=headers, json={"roles": ["manager"]})
    self_raised = other_client.put(f"/api/admin/users/{helpdesk_id}", headers=headers, json={"roles": ["owner"]})

    assert created.status_code == 403
    assert _error(created.json()) == "beyond_your_permissions"
    assert "role:manage" in created.json()["detail"]["permissions"]
    assert raised.status_code == 403
    assert _error(raised.json()) == "beyond_your_permissions"
    assert self_raised.status_code == 403


def test_user_admin_cannot_touch_a_stronger_user(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Rewriting a higher-ranked user's password would hand over all of their permissions."""
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
        r["id"] for r in client.get("/api/admin/roles", headers=admin_headers).json() if r["name"] == "owner"
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


# --- Do not change yourself ------------------------------------------------------


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
    """Only roles, active state and deletion are blocked. Resending the same roles is not a change."""
    admin_id = _admin_id(client, admin_headers)

    response = client.put(
        f"/api/admin/users/{admin_id}",
        headers=admin_headers,
        json={"username": "owner", "roles": ["owner"]},
    )

    assert response.status_code == 200, response.text


# --- Do not lose the last administrator ---------------------------------------------


def test_the_shared_administrator_role_cannot_be_hollowed_out(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Template roles are shared by every tenant, so a tenant administrator cannot change them (ADR-0079 §3)."""
    roles = client.get("/api/admin/roles", headers=admin_headers).json()
    admin_role = next(r for r in roles if r["name"] == "owner")
    without_core = [code for code in admin_role["permissions"] if code != "role:manage"]

    hollowed = client.put(
        f"/api/admin/roles/{admin_role['id']}", headers=admin_headers, json={"permissions": without_core}
    )
    deleted = client.delete(f"/api/admin/roles/{admin_role['id']}", headers=admin_headers)

    assert hollowed.status_code == 403
    assert _error(hollowed.json()) == "shared_role"
    assert deleted.status_code == 403
    after = next(r for r in client.get("/api/admin/roles", headers=admin_headers).json() if r["name"] == "owner")
    assert "role:manage" in after["permissions"]


def test_a_stale_token_cannot_disable_the_last_administrator(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Even after a role is removed, an access token in hand stays valid until it expires (ADR-0076 §5).

    Stopping the one remaining administrator with that old token would leave nobody able to re-grant permissions.
    """
    admin_id = _admin_id(client, admin_headers)
    second_id = _add_user(client, admin_headers, "second", ["owner"])
    second_headers = sign_in(other_client, "second@example.com", _PASSWORD)

    # second removes owner from the default administrator (second becomes the only active admin)
    demoted = other_client.put(f"/api/admin/users/{admin_id}", headers=second_headers, json={"roles": ["member"]})
    assert demoted.status_code == 200, demoted.text

    # The default administrator, still on the old token, tries to stop the last one
    response = client.put(f"/api/admin/users/{second_id}", headers=admin_headers, json={"is_active": False})

    assert response.status_code == 409
    assert _error(response.json()) == "last_administrator"
    users = other_client.get("/api/admin/users").json()
    assert next(u for u in users if u["id"] == second_id)["is_active"] is True
