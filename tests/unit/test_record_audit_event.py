"""``RecordAuditEvent`` の組み立てと、記録失敗時のふるまい。

監査ログが書けなくても本処理を落とさないことを機械で確かめる。ここが崩れると
「監査テーブルが無いだけでログインできない」状態になり得る。
"""

from __future__ import annotations

from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)


class RecordingSpy:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class FailingRecorder:
    def record(self, event: AuditEvent) -> None:
        raise RuntimeError("audit_log テーブルがありません")


_CONTEXT = AuditRequestContext(request_id="req-1", ip_address="203.0.113.7", user_agent="pytest")


def test_records_the_bound_request_context_and_actor() -> None:
    spy = RecordingSpy()
    RecordAuditEvent(spy, _CONTEXT, actor_user_id=7).execute(AuditEventType.LOGIN_SUCCEEDED)

    event = spy.events[0]
    assert event.event_type is AuditEventType.LOGIN_SUCCEEDED
    assert event.result is AuditResult.SUCCESS
    assert event.actor_user_id == 7
    assert event.context == _CONTEXT
    assert event.occurred_at.tzinfo is None  # 保存値は常に UTC の naive


def test_explicit_actor_wins_over_the_bound_one() -> None:
    """ログイン失敗のように、認証前の主体を呼び出し側が指定する場合。"""
    spy = RecordingSpy()
    RecordAuditEvent(spy, _CONTEXT).execute(
        AuditEventType.LOGIN_FAILED,
        AuditResult.FAILURE,
        actor_user_id=99,
        reason="invalid_password",
    )

    event = spy.events[0]
    assert event.actor_user_id == 99
    assert event.reason == "invalid_password"


def test_records_the_target() -> None:
    spy = RecordingSpy()
    RecordAuditEvent(spy, _CONTEXT, actor_user_id=1).execute(
        AuditEventType.USER_DELETED,
        target=AuditTarget.of(AuditTargetType.USER, 42),
    )

    target = spy.events[0].target
    assert target is not None
    assert (target.type, target.identifier) == (AuditTargetType.USER, "42")


def test_a_failing_recorder_does_not_break_the_caller() -> None:
    RecordAuditEvent(FailingRecorder(), _CONTEXT).execute(AuditEventType.LOGIN_SUCCEEDED)
