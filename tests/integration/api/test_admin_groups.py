"""グループ管理 API の統合テスト（ADR-0047）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import sign_in

_PASSWORD = "member-password-1"


def _create_member(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/admin/users",
        json={"email": f"{name}@example.com", "username": name, "password": _PASSWORD, "roles": ["member"]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_create_update_and_delete_a_group(client: TestClient, admin_headers: dict[str, str]) -> None:
    alice = _create_member(client, admin_headers, "alice")
    bob = _create_member(client, admin_headers, "bob")

    created = client.post(
        "/api/admin/groups",
        json={"name": " 経理 ", "description": "月末の締め", "member_ids": [alice]},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    group = created.json()
    assert group["name"] == "経理"
    assert [m["username"] for m in group["members"]] == ["alice"]

    updated = client.put(
        f"/api/admin/groups/{group['id']}", json={"member_ids": [alice, bob]}, headers=admin_headers
    ).json()
    assert [m["username"] for m in updated["members"]] == ["alice", "bob"]
    assert updated["description"] == "月末の締め"

    assert client.delete(f"/api/admin/groups/{group['id']}", headers=admin_headers).status_code == 204
    assert client.get("/api/admin/groups").json() == []


def test_names_are_unique(client: TestClient, admin_headers: dict[str, str]) -> None:
    client.post("/api/admin/groups", json={"name": "経理"}, headers=admin_headers)

    response = client.post("/api/admin/groups", json={"name": "経理"}, headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "group_already_exists"


def test_unknown_members_are_refused(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post("/api/admin/groups", json={"name": "経理", "member_ids": [999]}, headers=admin_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == {"error": "unknown_users", "users": [999]}


def test_deleting_a_user_takes_them_out_of_groups(client: TestClient, admin_headers: dict[str, str]) -> None:
    alice = _create_member(client, admin_headers, "alice")
    client.post("/api/admin/groups", json={"name": "経理", "member_ids": [alice]}, headers=admin_headers)

    assert client.delete(f"/api/admin/users/{alice}", headers=admin_headers).status_code == 204

    [group] = client.get("/api/admin/groups").json()
    assert group["members"] == []


def test_member_candidates_are_active_people(client: TestClient, admin_headers: dict[str, str]) -> None:
    alice = _create_member(client, admin_headers, "alice")
    client.put(f"/api/admin/users/{alice}", json={"is_active": False}, headers=admin_headers)

    candidates = client.get("/api/admin/groups/users").json()
    assert [c["username"] for c in candidates] == ["admin"]


def test_members_cannot_manage_groups(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _create_member(client, admin_headers, "alice")
    alice = sign_in(other_client, "alice@example.com", _PASSWORD)

    assert other_client.get("/api/admin/groups").status_code == 403
    assert other_client.post("/api/admin/groups", json={"name": "x"}, headers=alice).status_code == 403


def test_group_changes_are_audited(client: TestClient, admin_headers: dict[str, str]) -> None:
    alice = _create_member(client, admin_headers, "alice")
    client.post("/api/admin/groups", json={"name": "経理", "member_ids": [alice]}, headers=admin_headers)

    [event] = client.get("/api/admin/audit-logs", params={"event_type": "group.created"}).json()["entries"]
    assert event["reason"] == "members=1"
    assert event["target_type"] == "group"
