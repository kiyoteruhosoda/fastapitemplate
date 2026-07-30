"""監査イベントを記録するユースケース。

呼び出し側（ルーター）はリクエスト文脈を毎回組み立てず、リクエスト単位に束縛
された本ユースケースを ``Depends()`` で受け取る。``execute`` に渡すのは
「何をして、どうなったか」だけ。

記録の失敗で本処理を落とさない。監査ログが書けない状態（マイグレーション前など）
でもユーザー管理やログインを止めないため、失敗はアプリログへ残して続行する。
"""

from __future__ import annotations

import logging

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.repositories.audit_event_recorder import (
    AuditEventRecorder,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget
from shared.kernel.timestamps import utcnow

logger = logging.getLogger(__name__)


class RecordAuditEvent:
    """1 リクエスト分の文脈を持ち、そのリクエスト中の監査イベントを記録する。"""

    def __init__(
        self,
        recorder: AuditEventRecorder,
        context: AuditRequestContext,
        actor_user_id: int | None = None,
    ) -> None:
        self._recorder = recorder
        self._context = context
        self._actor_user_id = actor_user_id

    def execute(
        self,
        event_type: AuditEventType,
        result: AuditResult = AuditResult.SUCCESS,
        *,
        actor_user_id: int | None = None,
        target: AuditTarget | None = None,
        reason: str | None = None,
    ) -> None:
        """イベントを 1 件記録する。

        ``actor_user_id`` は省略時、リクエストの認証済み利用者（あれば）になる。
        認証前のイベント（ログイン失敗）では呼び出し側が明示的に渡す。

        ``reason`` には失敗理由や変更した項目名を入れる。**値そのもの（パスワード・
        メールアドレス等）は渡さない**（ADR-0008）。
        """
        event = AuditEvent(
            event_type=event_type,
            result=result,
            occurred_at=utcnow(),
            context=self._context,
            actor_user_id=actor_user_id if actor_user_id is not None else self._actor_user_id,
            target=target,
            reason=reason,
        )
        try:
            self._recorder.record(event)
        except Exception:
            logger.exception("監査イベントの記録に失敗しました", extra={"audit_event_type": str(event_type)})


__all__ = ["RecordAuditEvent"]
