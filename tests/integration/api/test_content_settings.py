"""コンテンツ設定の API（ADR-0085）と、それを読む見本（アイテムの一覧の並び順）。"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from tests.conftest import sign_in

_URL = "/api/admin/content-settings"


def _entries(client: TestClient) -> dict[str, dict[str, object]]:
    response = client.get(_URL)
    assert response.status_code == 200, response.text
    return {e["key"]: e for e in response.json()}


def _item_names(client: TestClient) -> list[str]:
    return [i["name"] for i in client.get("/api/items").json()["entries"]]


def test_unsaved_settings_show_their_default(client: TestClient, admin_headers: dict[str, str]) -> None:
    order = _entries(client)["item_list_order"]
    assert order["value"] == "oldest"
    assert order["default"] == "oldest"
    assert order["stored"] is False
    assert order["choices"] == ["oldest", "newest", "name"]


def test_the_items_list_follows_the_chosen_order(client: TestClient, admin_headers: dict[str, str]) -> None:
    for name in ("beta", "alpha", "gamma"):
        assert client.post("/api/items", json={"name": name}, headers=admin_headers).status_code == 201
    assert _item_names(client) == ["beta", "alpha", "gamma"]

    for order, expected in (("newest", ["gamma", "alpha", "beta"]), ("name", ["alpha", "beta", "gamma"])):
        saved = client.put(_URL, json={"values": {"item_list_order": order}}, headers=admin_headers)
        assert saved.status_code == 200, saved.text
        assert _item_names(client) == expected

    reset = client.put(_URL, json={"values": {"item_list_order": None}}, headers=admin_headers)
    assert {e["key"]: e for e in reset.json()}["item_list_order"]["stored"] is False
    assert _item_names(client) == ["beta", "alpha", "gamma"]


def test_values_outside_the_definition_change_nothing(client: TestClient, admin_headers: dict[str, str]) -> None:
    refused = client.put(_URL, json={"values": {"item_list_order": "name", "nope": 1}}, headers=admin_headers)
    assert refused.status_code == 422
    assert refused.json()["detail"] == {"error": "unknown_content_setting", "key": "nope"}
    invalid = client.put(_URL, json={"values": {"item_list_order": "random"}}, headers=admin_headers)
    assert invalid.json()["detail"]["error"] == "invalid_content_setting"
    assert _entries(client)["item_list_order"]["stored"] is False


def test_changes_are_audited_by_key_only(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    client.put(_URL, json={"values": {"item_list_order": "name"}}, headers=admin_headers)
    with Session(engine) as session:
        reasons = session.scalars(
            sa.select(AuditLogModel.reason).where(
                AuditLogModel.event_type == AuditEventType.CONTENT_SETTINGS_UPDATED.value
            )
        ).all()
    assert reasons == ["keys=item_list_order"]


def test_people_without_the_permission_are_refused(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "reader@example.com", "username": "reader", "password": "password-123", "roles": ["member"]},
    )
    assert created.status_code == 201, created.text
    headers = sign_in(other_client, "reader@example.com", "password-123")
    assert other_client.get(_URL).status_code == 403
    assert other_client.put(_URL, json={"values": {}}, headers=headers).status_code == 403


def test_the_auditor_reads_but_cannot_change(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"email": "audit@example.com", "username": "audit", "password": "password-123", "roles": ["auditor"]},
    )
    assert created.status_code == 201, created.text
    headers = sign_in(other_client, "audit@example.com", "password-123")
    assert other_client.get(_URL).status_code == 200
    changed = other_client.put(_URL, json={"values": {"item_list_order": "name"}}, headers=headers)
    assert changed.status_code == 403
