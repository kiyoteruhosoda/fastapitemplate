"""監査イベントの書き込みインターフェース（実装は Infrastructure 層）。

読み取り（:mod:`~bounded_contexts.audit.domain.repositories.audit_log_query`）と
分けている。書く側は「本処理のトランザクションに影響を与えず 1 件足す」だけが
責務で、検索条件・ページングを知る必要がない。
"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent


class AuditEventRecorder(Protocol):
    def record(self, event: AuditEvent) -> None:
        """*event* を 1 件記録する。

        実装は本処理と独立したトランザクションで書く。失敗したログイン試行の
        ように、リクエストがロールバックされても記録が残らなければならない
        イベントがあるため（ADR-0008）。
        """


__all__ = ["AuditEventRecorder"]
