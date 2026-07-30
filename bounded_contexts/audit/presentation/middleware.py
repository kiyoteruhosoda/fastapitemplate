"""監査イベントの書き込みミドルウェア。

リクエスト中に控えたイベントを、**リクエストの処理が完全に終わってから**まとめて書く。

この位置で書く理由は 2 つ（ADR-0010）。

1. **失敗したログインを残すため。** リクエストのセッションで書くと、401 の
   ロールバックで最も記録したいイベントが消える。
2. **SQLite で書き込みロックと競合しないため。** 処理の途中で別コネクションから
   書くと、リクエストのセッションが握った書き込みロックと衝突して
   ``database is locked`` になる（既定の ``sqlite:///app.db`` で必ず起きる）。

**素の ASGI ミドルウェアとして書いている**（``BaseHTTPMiddleware`` を使わない）。
FastAPI は ``yield`` を使う依存（``get_db`` の commit）をレスポンス送出の**後**に
閉じるが、``BaseHTTPMiddleware`` の ``call_next`` はレスポンスの先頭を受け取った
時点で戻ってくる。それでは commit 前に書きに行ってしまい、上記 2 の競合が起きる。
``await self.app(...)`` は下流を最後まで待つので、セッションが閉じた後になる。

例外で抜けた場合も書く。控えたイベントはそれぞれが自分の成否（``result``）を
持っており、リクエストが落ちたことと記録の要否は別だから。
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from bounded_contexts.audit.application.use_cases.write_audit_events import (
    WriteAuditEvents,
)
from bounded_contexts.audit.infrastructure.sql_audit_log_repository import (
    SqlAuditEventRecorder,
)
from bounded_contexts.audit.presentation.pending_events import install_pending_events


class AuditRecordingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        pending = install_pending_events()
        try:
            await self.app(scope, receive, send)
        finally:
            WriteAuditEvents(SqlAuditEventRecorder()).execute(pending.drain())


__all__ = ["AuditRecordingMiddleware"]
