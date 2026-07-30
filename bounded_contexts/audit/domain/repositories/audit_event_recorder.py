"""監査イベントの収集・書き込みインターフェース（実装は外側の層）。

収集と書き込みを分けている。**収集は I/O を伴わず失敗しない**（処理の途中で呼ばれる）
のに対し、**書き込みは I/O で失敗し得る**（リクエストの処理が終わってから一度だけ
行う）。責務が違うので同じ口にまとめない。

分けたもう 1 つの理由は SQLite（ADR-0001 で開発・テストの DB として使う）。処理の
途中で別コネクションから書こうとすると、リクエストのセッションが持つ書き込みロック
と衝突して `database is locked` になる。書き込みをリクエストの外へ出すことで、
ロックの競合そのものを無くしている（ADR-0013）。

読み取りは :mod:`~bounded_contexts.audit.domain.repositories.audit_log_query`。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent


class AuditEventCollector(Protocol):
    """処理の途中で発生した監査イベントを控える先。"""

    def add(self, event: AuditEvent) -> None:
        """*event* を控えに積む。I/O を行わないため失敗しない。"""


class AuditEventRecorder(Protocol):
    """控えた監査イベントを永続化する先。"""

    def record_all(self, events: Sequence[AuditEvent]) -> None:
        """*events* を発生順に 1 トランザクションで書き込む。

        呼び出し元の処理（リクエスト）は既に終わっている。失敗したログイン試行の
        ように、リクエストがロールバックされたイベントもここで書かれる。
        """


__all__ = ["AuditEventCollector", "AuditEventRecorder"]
