"""アプリログ（``log`` テーブル）のまとめ書きミドルウェア。

リクエスト中に出たログ行を、**リクエストの処理が完全に終わってから**一度に書く。
処理の途中で別コネクションから INSERT すると、リクエストのセッションが握った
書き込みロックと衝突し、SQLite では busy timeout（5 秒）の末に行が失われる
（:mod:`shared.kernel.logging.pending_records`）。

**素の ASGI ミドルウェアとして書いている**（``BaseHTTPMiddleware`` を使わない）。
FastAPI は ``yield`` を使う依存（``get_db`` の commit）をレスポンス送出の**後**に
閉じるため、``call_next`` が戻った時点ではまだセッションが開いている。
``await self.app(...)`` は下流を最後まで待つので、確実に commit / rollback の後になる。

監査ログにも同じ仕組みがあるが、書き込みの持ち主が違うので分けている
（アプリログはロギング基盤、監査ログは audit コンテキスト。ADR-0008）。
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from shared.kernel.logging.db_log_handler import write_log_rows
from shared.kernel.logging.pending_records import install_pending_log_records

# このロガーは DbLogHandler の除外対象（``shared.kernel.logging`` 配下）。
# 書き込み失敗のログがまた書き込みを誘発しないようにするため。
logger = logging.getLogger("shared.kernel.logging.deferred_writes")


class DeferredLogWriteMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        pending = install_pending_log_records()
        try:
            await self.app(scope, receive, send)
        finally:
            try:
                write_log_rows(pending.drain())
            except Exception:
                # DB へ書けなくても stdout の構造化ログは出ている。処理は止めない
                logger.exception("ログの DB 書き込みに失敗しました")


__all__ = ["DeferredLogWriteMiddleware"]
