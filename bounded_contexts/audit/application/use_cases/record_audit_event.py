"""監査イベントを組み立てて控えに積むユースケース。

呼び出し側（ルーター）はリクエスト文脈を毎回組み立てず、リクエスト単位に束縛
された本ユースケースを ``Depends()`` で受け取る。``execute`` に渡すのは
「何をして、どうなったか」だけ。

**ここでは DB へ書かない。** 控えに積むだけで、実際の書き込みはリクエストの処理が
終わってから :class:`~bounded_contexts.audit.application.use_cases.write_audit_events.WriteAuditEvents`
がまとめて行う（ADR-0008）。処理の途中で別コネクションから書くと、SQLite では
リクエストのセッションが持つ書き込みロックと衝突するため。
"""

from __future__ import annotations

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEvent,
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.repositories.audit_event_recorder import (
    AuditEventCollector,
)
from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget
from shared.kernel.timestamps import utcnow


class RecordAuditEvent:
    """1 リクエスト分の文脈を持ち、そのリクエスト中の監査イベントを組み立てる。"""

    def __init__(
        self,
        collector: AuditEventCollector,
        context: AuditRequestContext,
        actor_user_id: int | None = None,
    ) -> None:
        self._collector = collector
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
        """イベントを 1 件記録する（書き込みはリクエスト終了後）。

        ``actor_user_id`` は**認証済みの実行者**。省略時はリクエストの認証済み利用者
        で、未認証のリクエストでは ``None`` のままになる。「誰がやったか分からないが
        誰に対しての操作かは分かる」場合（ログイン失敗・パスワードリセット）は、
        主体ではなく ``target`` に相手を入れる（ADR-0008）。

        ``reason`` には失敗理由や変更した項目名を入れる。**値そのもの（パスワード・
        メールアドレス等）は渡さない**。
        """
        self._collector.add(
            AuditEvent(
                event_type=event_type,
                result=result,
                occurred_at=utcnow(),
                context=self._context,
                actor_user_id=actor_user_id if actor_user_id is not None else self._actor_user_id,
                target=target,
                reason=reason,
            )
        )


__all__ = ["RecordAuditEvent"]
