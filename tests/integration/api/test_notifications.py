"""お知らせの配信と手元（ベル・画面上部）の統合テスト（ADR-0047）。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from bounded_contexts.notification.domain.entities.push_subscription import PushSubscription
from bounded_contexts.notification.domain.services.push_sender import PushMessage, PushOutcome, PushSender
from bounded_contexts.notification.presentation.dependencies import get_push_sender
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


def _send(client: TestClient, headers: dict[str, str], **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "メンテナンスのお知らせ",
        "body": "今夜 22 時から止まります",
        "link_url": "/items",
        "channels": ["bell", "banner"],
        "audience": {"kind": "all"},
    }
    body.update(overrides)
    response = client.post("/api/admin/notifications", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


class _FakePushSender(PushSender):
    def __init__(self, outcome: PushOutcome = PushOutcome.DELIVERED) -> None:
        self.outcome = outcome
        self.sent: list[tuple[str, PushMessage]] = []

    @property
    def enabled(self) -> bool:
        return True

    def public_key(self) -> str | None:
        return "BPublicKeyForTests"

    def send(self, subscription: PushSubscription, message: PushMessage) -> PushOutcome:
        self.sent.append((subscription.endpoint, message))
        return self.outcome


@pytest.fixture
def push_sender(client: TestClient) -> Iterator[_FakePushSender]:
    fake = _FakePushSender()
    client.app.dependency_overrides[get_push_sender] = lambda: fake  # type: ignore[attr-defined]
    yield fake
    client.app.dependency_overrides.pop(get_push_sender, None)  # type: ignore[attr-defined]


def test_everyone_finds_it_in_the_bell_and_can_read_it(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _create_member(client, admin_headers, "alice")
    sent = _send(client, admin_headers)
    assert sent["recipient_count"] == 2  # 管理者と alice
    notification_id = sent["notification"]["id"]  # type: ignore[index]

    alice = sign_in(other_client, "alice@example.com", _PASSWORD)
    inbox = other_client.get("/api/notifications").json()
    assert inbox["unread_count"] == 1
    [item] = inbox["items"]
    assert item["title"] == "メンテナンスのお知らせ"
    assert item["channels"] == ["banner", "bell"]
    assert item["link_url"] == "/items"
    assert item["read_at"] is None

    assert other_client.post(f"/api/notifications/{notification_id}/read", headers=alice).status_code == 204
    inbox = other_client.get("/api/notifications").json()
    assert inbox["unread_count"] == 0
    assert inbox["items"][0]["read_at"] is not None
    assert inbox["items"][0]["dismissed_at"] is None


def test_dismissing_the_banner_also_marks_it_read(client: TestClient, admin_headers: dict[str, str]) -> None:
    notification_id = _send(client, admin_headers)["notification"]["id"]  # type: ignore[index]

    assert client.post(f"/api/notifications/{notification_id}/dismiss", headers=admin_headers).status_code == 204

    [item] = client.get("/api/notifications").json()["items"]
    assert item["dismissed_at"] is not None
    assert item["read_at"] is not None


def test_read_all(client: TestClient, admin_headers: dict[str, str]) -> None:
    _send(client, admin_headers)
    _send(client, admin_headers, title="2 通目")

    assert client.post("/api/notifications/read-all", headers=admin_headers).status_code == 204
    assert client.get("/api/notifications").json()["unread_count"] == 0


def test_a_banner_only_notice_does_not_count_in_the_bell(client: TestClient, admin_headers: dict[str, str]) -> None:
    _send(client, admin_headers, channels=["banner"])

    inbox = client.get("/api/notifications").json()
    assert inbox["unread_count"] == 0
    assert len(inbox["items"]) == 1


def test_a_group_notice_reaches_only_its_members(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    alice = _create_member(client, admin_headers, "alice")
    _create_member(client, admin_headers, "bob")
    group = client.post("/api/admin/groups", json={"name": "経理", "member_ids": [alice]}, headers=admin_headers).json()

    sent = _send(client, admin_headers, audience={"kind": "group", "target_id": group["id"]})
    assert sent["recipient_count"] == 1

    sign_in(other_client, "bob@example.com", _PASSWORD)
    assert other_client.get("/api/notifications").json()["items"] == []
    sign_in(other_client, "alice@example.com", _PASSWORD)
    assert len(other_client.get("/api/notifications").json()["items"]) == 1


def test_a_personal_notice(client: TestClient, other_client: TestClient, admin_headers: dict[str, str]) -> None:
    alice = _create_member(client, admin_headers, "alice")

    sent = _send(client, admin_headers, audience={"kind": "user", "target_id": alice})
    assert sent["recipient_count"] == 1

    assert client.get("/api/notifications").json()["items"] == []  # 管理者には届かない
    sign_in(other_client, "alice@example.com", _PASSWORD)
    assert len(other_client.get("/api/notifications").json()["items"]) == 1


def test_someone_elses_notice_cannot_be_touched(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    alice = _create_member(client, admin_headers, "alice")
    _create_member(client, admin_headers, "bob")
    notification_id = _send(client, admin_headers, audience={"kind": "user", "target_id": alice})["notification"][
        "id"  # type: ignore[index]
    ]

    bob = sign_in(other_client, "bob@example.com", _PASSWORD)
    response = other_client.post(f"/api/notifications/{notification_id}/read", headers=bob)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "notification_not_found"


@pytest.mark.parametrize(
    ("overrides", "status_code", "error"),
    [
        ({"link_url": "javascript:alert(1)"}, 400, "link_not_allowed"),
        ({"link_url": "//evil.example/"}, 400, "link_not_allowed"),
        ({"audience": {"kind": "group", "target_id": 999}}, 404, "group_not_found"),
        ({"audience": {"kind": "user", "target_id": 999}}, 404, "user_not_found"),
        ({"audience": {"kind": "group"}}, 400, "audience_target_required"),
        ({"channels": ["push"]}, 400, "push_not_configured"),
    ],
)
def test_bad_notices_are_refused(
    client: TestClient, admin_headers: dict[str, str], overrides: dict[str, object], status_code: int, error: str
) -> None:
    body: dict[str, object] = {"title": "x", "channels": ["bell"], "audience": {"kind": "all"}, **overrides}
    response = client.post("/api/admin/notifications", json=body, headers=admin_headers)
    assert response.status_code == status_code, response.text
    assert response.json()["detail"]["error"] == error


def test_an_empty_group_is_refused(client: TestClient, admin_headers: dict[str, str]) -> None:
    group = client.post("/api/admin/groups", json={"name": "空"}, headers=admin_headers).json()

    response = client.post(
        "/api/admin/notifications",
        json={"title": "x", "channels": ["bell"], "audience": {"kind": "group", "target_id": group["id"]}},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "no_recipients"


def test_members_cannot_send(client: TestClient, other_client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_member(client, admin_headers, "alice")
    alice = sign_in(other_client, "alice@example.com", _PASSWORD)

    body = {"title": "x", "channels": ["bell"], "audience": {"kind": "all"}}
    assert other_client.post("/api/admin/notifications", json=body, headers=alice).status_code == 403
    assert other_client.get("/api/admin/notifications").status_code == 403


def test_the_history_counts_recipients_and_readers(client: TestClient, admin_headers: dict[str, str]) -> None:
    _create_member(client, admin_headers, "alice")
    notification_id = _send(client, admin_headers)["notification"]["id"]  # type: ignore[index]
    client.post(f"/api/notifications/{notification_id}/read", headers=admin_headers)

    [sent] = client.get("/api/admin/notifications").json()
    assert sent["recipient_count"] == 2
    assert sent["read_count"] == 1
    assert sent["audience"] == {"kind": "all", "target_id": None}


def test_sending_is_audited(client: TestClient, admin_headers: dict[str, str]) -> None:
    _send(client, admin_headers)

    events = client.get("/api/admin/audit-logs", params={"event_type": "notification.sent"}).json()
    [event] = events["entries"]
    assert event["reason"] == "audience=all channels=banner,bell recipients=1"


def test_audience_options_list_groups_and_active_people(client: TestClient, admin_headers: dict[str, str]) -> None:
    alice = _create_member(client, admin_headers, "alice")
    client.post("/api/admin/groups", json={"name": "経理", "member_ids": [alice]}, headers=admin_headers)

    options = client.get("/api/admin/notifications/audiences").json()
    assert [(g["name"], g["member_count"]) for g in options["groups"]] == [("経理", 1)]
    assert {u["username"] for u in options["users"]} == {"admin", "alice"}


# --- 端末への通知 ---------------------------------------------------------------

_ENDPOINT = "https://push.example.test/v1/device-1"
_KEYS = {"p256dh": "BKeyForTests", "auth": "authForTests"}


def test_push_is_off_without_a_key(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get("/api/notifications/push").json() == {"enabled": False, "public_key": None}
    response = client.post(
        "/api/notifications/push/subscribe", json={"endpoint": _ENDPOINT, "keys": _KEYS}, headers=admin_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "push_not_configured"


def test_a_subscribed_device_receives_the_push(
    client: TestClient, admin_headers: dict[str, str], push_sender: _FakePushSender
) -> None:
    assert client.get("/api/notifications/push").json() == {"enabled": True, "public_key": "BPublicKeyForTests"}
    response = client.post(
        "/api/notifications/push/subscribe", json={"endpoint": _ENDPOINT, "keys": _KEYS}, headers=admin_headers
    )
    assert response.status_code == 204
    status = client.post("/api/notifications/push/status", json={"endpoint": _ENDPOINT}, headers=admin_headers)
    assert status.json() == {"subscribed": True}

    sent = _send(client, admin_headers, channels=["push"])

    assert sent["push_scheduled"] is True
    [(endpoint, message)] = push_sender.sent
    assert endpoint == _ENDPOINT
    assert message.title == "メンテナンスのお知らせ"
    assert message.link_url == "/items"
    # 端末への通知だけのものは、ベルにも上部にも出ない
    assert client.get("/api/notifications").json()["items"] == []


def test_a_gone_subscription_is_dropped(
    client: TestClient, admin_headers: dict[str, str], push_sender: _FakePushSender
) -> None:
    client.post("/api/notifications/push/subscribe", json={"endpoint": _ENDPOINT, "keys": _KEYS}, headers=admin_headers)
    push_sender.outcome = PushOutcome.GONE

    _send(client, admin_headers, channels=["push", "bell"])

    status = client.post("/api/notifications/push/status", json={"endpoint": _ENDPOINT}, headers=admin_headers)
    assert status.json() == {"subscribed": False}


def test_unsubscribing(client: TestClient, admin_headers: dict[str, str], push_sender: _FakePushSender) -> None:
    client.post("/api/notifications/push/subscribe", json={"endpoint": _ENDPOINT, "keys": _KEYS}, headers=admin_headers)

    response = client.post("/api/notifications/push/unsubscribe", json={"endpoint": _ENDPOINT}, headers=admin_headers)
    assert response.status_code == 204

    _send(client, admin_headers, channels=["push"])
    assert push_sender.sent == []


def test_a_plain_http_endpoint_is_refused(
    client: TestClient, admin_headers: dict[str, str], push_sender: _FakePushSender
) -> None:
    """endpoint はサーバーが POST しに行く先。https 以外を受けると内側の URL を叩かされる。"""
    response = client.post(
        "/api/notifications/push/subscribe",
        json={"endpoint": "http://127.0.0.1:8000/api/admin/users", "keys": _KEYS},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_push_endpoint"


def test_signing_in_is_required(client: TestClient) -> None:
    assert client.get("/api/notifications").status_code == 401
