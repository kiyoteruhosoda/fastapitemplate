"""共有メモ API の統合テスト（ADR-0078 §6）。

認可の 2 段を確かめる。

- 機能を使えるか —— トークンの scope（``note:view`` / ``note:write``）
- この 1 件を扱えるか —— 持ち主とグループの所属（DB）
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from typing import Protocol

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import sign_in

_PASSWORD = "notes-password-1"

Side = tuple[TestClient, dict[str, str]]


class SignUp(Protocol):
    def __call__(self, name: str, role: str) -> tuple[int, Side]: ...


@pytest.fixture
def sign_up(app: FastAPI, client: TestClient, admin_headers: dict[str, str]) -> Iterator[SignUp]:
    """管理者が利用者を作り、その人として入った別のブラウザを返す。"""
    with ExitStack() as stack:

        def _sign_up(name: str, role: str) -> tuple[int, Side]:
            response = client.post(
                "/api/admin/users",
                json={"email": f"{name}@example.com", "username": name, "password": _PASSWORD, "roles": [role]},
                headers=admin_headers,
            )
            assert response.status_code == 201, response.text
            browser = stack.enter_context(TestClient(app))
            return int(response.json()["id"]), (browser, sign_in(browser, f"{name}@example.com", _PASSWORD))

        yield _sign_up


def _group(client: TestClient, admin_headers: dict[str, str], name: str, member_ids: list[int]) -> int:
    response = client.post("/api/admin/groups", json={"name": name, "member_ids": member_ids}, headers=admin_headers)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _write(side: Side, title: str, group_id: int | None = None) -> int:
    browser, headers = side
    response = browser.post("/api/notes", json={"title": title, "shared_group_id": group_id}, headers=headers)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _titles(side: Side) -> list[str]:
    response = side[0].get("/api/notes")
    assert response.status_code == 200, response.text
    return [note["title"] for note in response.json()]


def test_a_private_note_is_seen_only_by_its_owner(sign_up: SignUp) -> None:
    _, alice = sign_up("alice", "manager")
    _, bob = sign_up("bob", "manager")
    note_id = _write(alice, "alice only")

    assert _titles(alice) == ["alice only"]
    assert _titles(bob) == []
    # 読めないメモは「無い」と答える（在ることも漏らさない）
    browser, headers = bob
    assert browser.get(f"/api/notes/{note_id}").json()["detail"]["error"] == "note_not_found"
    response = browser.put(f"/api/notes/{note_id}", json={"title": "taken"}, headers=headers)
    assert response.status_code == 404


def test_group_members_read_a_shared_note_but_only_the_owner_changes_it(
    sign_up: SignUp, client: TestClient, admin_headers: dict[str, str]
) -> None:
    alice_id, alice = sign_up("alice", "manager")
    bob_id, bob = sign_up("bob", "manager")
    _, dave = sign_up("dave", "manager")
    group_id = _group(client, admin_headers, "家族", [alice_id, bob_id])
    note_id = _write(alice, "shared", group_id)

    shared = bob[0].get(f"/api/notes/{note_id}").json()
    assert (shared["mine"], shared["can_change"]) == (False, False)
    assert [(n["id"], n["can_change"]) for n in bob[0].get("/api/notes").json()] == [(note_id, False)]

    # bob も note:write を持つ（機能は使える）が、この 1 件は alice のもの
    browser, headers = bob
    response = browser.put(f"/api/notes/{note_id}", json={"title": "edited by bob"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["error"]) == (403, "note_not_owned")
    assert browser.delete(f"/api/notes/{note_id}", headers=headers).status_code == 403

    # グループの外の人には無い
    assert _titles(dave) == []
    assert dave[0].get(f"/api/notes/{note_id}").status_code == 404


def test_the_owner_edits_and_deletes(sign_up: SignUp) -> None:
    _, alice = sign_up("alice", "manager")
    note_id = _write(alice, "draft")
    browser, headers = alice

    response = browser.put(f"/api/notes/{note_id}", json={"title": "final", "body": "本文"}, headers=headers)
    assert response.status_code == 200, response.text
    assert (response.json()["title"], response.json()["body"], response.json()["can_change"]) == ("final", "本文", True)

    assert browser.delete(f"/api/notes/{note_id}", headers=headers).status_code == 204
    assert _titles(alice) == []


def test_the_scope_gates_the_feature_before_any_note_is_looked_at(sign_up: SignUp) -> None:
    _, carol = sign_up("carol", "member")
    _, gus = sign_up("gus", "guest")

    # member は note:view だけ。書く機能はトークンの時点で断られる
    browser, headers = carol
    response = browser.post("/api/notes", json={"title": "x"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["error"]) == (403, "forbidden")
    assert browser.get("/api/notes").status_code == 200
    # guest は機能そのものを使えない
    assert gus[0].get("/api/notes").status_code == 403


def test_leaving_the_group_hides_the_note_without_a_new_token(
    sign_up: SignUp, client: TestClient, admin_headers: dict[str, str]
) -> None:
    alice_id, alice = sign_up("alice", "manager")
    carol_id, carol = sign_up("carol", "member")
    group_id = _group(client, admin_headers, "家族", [alice_id, carol_id])
    _write(alice, "shared", group_id)
    assert _titles(carol) == ["shared"]

    response = client.put(f"/api/admin/groups/{group_id}", json={"member_ids": [alice_id]}, headers=admin_headers)
    assert response.status_code == 200, response.text

    # carol のトークンはそのまま（更新していない）。所属は DB で見るので、すぐ効く
    assert _titles(carol) == []


def test_sharing_is_limited_to_your_own_groups(
    sign_up: SignUp, client: TestClient, admin_headers: dict[str, str]
) -> None:
    alice_id, alice = sign_up("alice", "manager")
    bob_id, _ = sign_up("bob", "manager")
    mine = _group(client, admin_headers, "家族", [alice_id])
    theirs = _group(client, admin_headers, "経理", [bob_id])

    browser, headers = alice
    assert browser.get("/api/notes/share-targets").json() == [{"id": mine, "name": "家族"}]
    response = browser.post("/api/notes", json={"title": "x", "shared_group_id": theirs}, headers=headers)
    assert (response.status_code, response.json()["detail"]["error"]) == (422, "share_group_not_joined")


def test_the_owner_keeps_the_share_after_leaving_the_group(
    sign_up: SignUp, client: TestClient, admin_headers: dict[str, str]
) -> None:
    alice_id, alice = sign_up("alice", "manager")
    bob_id, bob = sign_up("bob", "manager")
    group_id = _group(client, admin_headers, "家族", [alice_id, bob_id])
    note_id = _write(alice, "shared", group_id)
    client.put(f"/api/admin/groups/{group_id}", json={"member_ids": [bob_id]}, headers=admin_headers)

    browser, headers = alice
    response = browser.put(
        f"/api/notes/{note_id}", json={"title": "renamed", "shared_group_id": group_id}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert _titles(bob) == ["renamed"]


def test_blank_titles_are_refused(sign_up: SignUp) -> None:
    browser, headers = sign_up("alice", "manager")[1]
    assert browser.post("/api/notes", json={"title": "   "}, headers=headers).status_code == 422
