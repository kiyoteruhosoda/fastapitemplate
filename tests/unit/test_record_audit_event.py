"""``RecordAuditEvent`` の組み立てと、``WriteAuditEvents`` の失敗時のふるまい。

記録は 2 段階に分かれている（ADR-0013）。

- 処理の途中: :class:`RecordAuditEvent` が組み立てて控えに積む（I/O なし・失敗しない）
- 処理の後: :class:`WriteAuditEvents` がまとめて書く（失敗しても呼び出し元を落とさない）

監査ログが書けないだけでログインできなくなる、という状態にしないための分割。
"""

from __future__ import annotations

from collections.abc import Sequence

from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.application.use_cases.write_audit_events import (
    WriteAuditEvents,
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
from bounded_contexts.audit.presentation.pending_events import PendingAuditEvents


class RecordingSpy:
    def __init__(self) -> None:
        self.written: list[AuditEvent] = []

    def record_all(self, events: Sequence[AuditEvent]) -> None:
        self.written.extend(events)


class FailingRecorder:
    def record_all(self, events: Sequence[AuditEvent]) -> None:
        raise RuntimeError("audit_log テーブルがありません")


_CONTEXT = AuditRequestContext(request_id="req-1", ip_address="203.0.113.7", user_agent="pytest")


def test_records_the_bound_request_context_and_actor() -> None:
    pending = PendingAuditEvents()
    RecordAuditEvent(pending, _CONTEXT, actor_user_id=7).execute(AuditEventType.LOGIN_SUCCEEDED)

    event = pending.drain()[0]
    assert event.event_type is AuditEventType.LOGIN_SUCCEEDED
    assert event.result is AuditResult.SUCCESS
    assert event.actor_user_id == 7
    assert event.context == _CONTEXT
    assert event.occurred_at.tzinfo is None  # 保存値は常に UTC の naive


def test_as_actor_rebinds_the_actor() -> None:
    """ログインのように、実行者が処理の最中に確定する場合。"""
    pending = PendingAuditEvents()
    recorder = RecordAuditEvent(pending, _CONTEXT)

    recorder.as_actor(99).execute(AuditEventType.LOGIN_SUCCEEDED)
    # 元の記録口は据え置き（束ね直した方だけが実行者を持つ）
    recorder.execute(AuditEventType.PASSWORD_CHANGED, AuditResult.FAILURE, reason="invalid_current_password")

    rebound, original = pending.drain()
    assert rebound.actor_user_id == 99
    assert original.actor_user_id is None
    assert original.reason == "invalid_current_password"


def test_unauthenticated_events_have_no_actor() -> None:
    """未認証のリクエストでは実行者を空のままにする（相手は target で表す）。"""
    pending = PendingAuditEvents()
    RecordAuditEvent(pending, _CONTEXT).execute(
        AuditEventType.LOGIN_FAILED,
        AuditResult.FAILURE,
        target=AuditTarget.of(AuditTargetType.USER, 42),
        reason="invalid_password",
    )

    event = pending.drain()[0]
    assert event.actor_user_id is None
    assert event.target == AuditTarget.of(AuditTargetType.USER, 42)


def test_records_the_target() -> None:
    pending = PendingAuditEvents()
    RecordAuditEvent(pending, _CONTEXT, actor_user_id=1).execute(
        AuditEventType.USER_DELETED,
        target=AuditTarget.of(AuditTargetType.USER, 42),
    )

    target = pending.drain()[0].target
    assert target is not None
    assert (target.type, target.identifier) == (AuditTargetType.USER, "42")


def test_pending_events_keep_the_order_and_drain_once() -> None:
    """控えは発生順に保たれ、取り出したら空になる（二重書き込みを防ぐ）。"""
    pending = PendingAuditEvents()
    recorder = RecordAuditEvent(pending, _CONTEXT, actor_user_id=1)
    recorder.execute(AuditEventType.USER_CREATED)
    recorder.execute(AuditEventType.USER_UPDATED)

    assert [e.event_type for e in pending.drain()] == [
        AuditEventType.USER_CREATED,
        AuditEventType.USER_UPDATED,
    ]
    assert pending.drain() == ()


def test_writes_the_collected_events_in_one_call() -> None:
    pending = PendingAuditEvents()
    recorder = RecordAuditEvent(pending, _CONTEXT, actor_user_id=1)
    recorder.execute(AuditEventType.USER_CREATED)
    recorder.execute(AuditEventType.USER_DELETED)

    spy = RecordingSpy()
    WriteAuditEvents(spy).execute(pending.drain())

    assert [e.event_type for e in spy.written] == [
        AuditEventType.USER_CREATED,
        AuditEventType.USER_DELETED,
    ]


def test_a_failing_recorder_does_not_break_the_caller() -> None:
    pending = PendingAuditEvents()
    RecordAuditEvent(pending, _CONTEXT).execute(AuditEventType.LOGIN_SUCCEEDED)

    WriteAuditEvents(FailingRecorder()).execute(pending.drain())


def test_nothing_to_write_touches_no_recorder() -> None:
    WriteAuditEvents(FailingRecorder()).execute(())
