"""リクエスト中に発生した監査イベントの控え。

監査イベントは処理の途中で発生するが、**書き込みはリクエストの処理が終わってから**
行う（ADR-0013）。その間、イベントをここに溜める。

控えは ``contextvars`` で運ぶ。ログや監査は横断的関心事で、途中の全関数へ引き回すと
本来の責務が埋もれるため（:mod:`shared.kernel.logging.request_context` と同じ理由）。

ミドルウェアが**控えの実体を作ってから**下流を呼び、同じオブジェクトを両側で使う。
``ContextVar.set()`` の結果に依存せず、可変オブジェクトの共有で受け渡すことで、
下流が別タスクで動く構成（``BaseHTTPMiddleware`` を挟む等）でも取りこぼさない。
"""

from __future__ import annotations

from contextvars import ContextVar

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent


class PendingAuditEvents:
    """1 リクエスト分の控え（Domain の ``AuditEventCollector`` の実装）。

    I/O を行わないので失敗しない。処理の途中で監査の都合により例外を出さないための
    分割でもある（書き込みの失敗は ``WriteAuditEvents`` が引き受ける）。
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self._events.append(event)

    def drain(self) -> tuple[AuditEvent, ...]:
        """控えを取り出して空にする（二重書き込みを防ぐ）。"""
        events = tuple(self._events)
        self._events.clear()
        return events


_pending_events_var: ContextVar[PendingAuditEvents | None] = ContextVar("pending_audit_events", default=None)


def install_pending_events() -> PendingAuditEvents:
    """このリクエストの控えを用意して返す（ミドルウェアが最初に呼ぶ）。"""
    pending = PendingAuditEvents()
    _pending_events_var.set(pending)
    return pending


def current_pending_events() -> PendingAuditEvents | None:
    """処理中のリクエストの控え。ミドルウェアの外（スクリプト等）では ``None``。"""
    return _pending_events_var.get()


__all__ = ["PendingAuditEvents", "current_pending_events", "install_pending_events"]
