"""控えた監査イベントを永続化するユースケース。

リクエストの処理（DB セッションの commit / rollback）が完全に終わってから、1 回だけ
呼ばれる。この時点でリクエストのトランザクションは閉じているため、SQLite でも書き
込みロックが競合しない（ADR-0013）。

書き込みの失敗で呼び出し元を落とさない。監査ログが書けない状態（マイグレーション前・
DB 障害）でも、既に返したレスポンスを取り消すことはできないため、失敗はアプリログへ
残して続行する。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from bounded_contexts.audit.domain.entities.audit_event import AuditEvent
from bounded_contexts.audit.domain.repositories.audit_event_recorder import (
    AuditEventRecorder,
)

logger = logging.getLogger(__name__)


class WriteAuditEvents:
    def __init__(self, recorder: AuditEventRecorder) -> None:
        self._recorder = recorder

    def execute(self, events: Sequence[AuditEvent]) -> None:
        if not events:
            return
        try:
            self._recorder.record_all(events)
        except Exception:
            logger.exception(
                "監査イベントの記録に失敗しました",
                extra={"audit_event_count": len(events)},
            )


__all__ = ["WriteAuditEvents"]
