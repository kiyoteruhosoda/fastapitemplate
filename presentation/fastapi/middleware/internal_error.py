"""想定外の例外を、通常の応答としてミドルウェアの内側で受け止める。

``Exception`` ハンドラだけでは足りない。Starlette はそれを
``ServerErrorMiddleware``（全ミドルウェアの**外側**）へ載せるため、そこで作った
応答は CORS ミドルウェアもリクエストログミドルウェアも通らない。結果として

- 別オリジンのフロントエンドでは ``Access-Control-Allow-Origin`` が付かず、
  ブラウザが本文を捨てる。せっかくのエラーコードが読まれず ``unknown_error``
  に戻ってしまう。
- アクセスログに 500 の行が残らない（例外が記録層を素通りするため）。
- アプリログ・監査ログのまとめ書きが走らず、そのリクエストで出たログ行ごと
  失われる（まとめ書きのミドルウェアも外側にいるため）。

このミドルウェアを最も内側に置き、例外をここで応答へ変えることで、以降の
ミドルウェアからは「ふつうの 500 応答」に見えるようにする。

**素の ASGI ミドルウェアとして書いている**（``BaseHTTPMiddleware`` を使わない）。
``BaseHTTPMiddleware`` は下流を**別のタスク**で走らせるため、そこで設定された
``contextvars`` が ``dispatch`` 側へ伝わらない。認証依存関数が設定する
``user_id_hash``（:mod:`shared.kernel.logging.request_context`）がまさにそれで、
``BaseHTTPMiddleware`` のままだと 500 のログ行だけ「誰のリクエストか」が空になる。
``await self.app(...)`` は同じタスクで下流を待つので、認証済みの文脈がそのまま
記録に乗る。
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from presentation.fastapi.error_handling import (
    internal_error_response,
    log_unhandled_exception,
)


class InternalErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = _ResponseStarted()
        try:
            await self.app(scope, receive, started.watching(send))
        except Exception as error:
            # 最後の受け皿なので、ここでは種類を問わず握って応答へ変える。
            request = Request(scope)
            if started.value:
                # ヘッダーを送り出した後は応答を差し替えられない。記録だけ残して
                # 投げ直す（外側の ServerErrorMiddleware が接続を閉じる）。
                log_unhandled_exception(request, error)
                raise
            response = internal_error_response(request, error)
            await response(scope, receive, send)


class _ResponseStarted:
    """応答の送出が始まったかを覚える（差し替え可能かの判断に使う）。"""

    def __init__(self) -> None:
        self.value = False

    def watching(self, send: Send) -> Send:
        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.value = True
            await send(message)

        return _send


__all__ = ["InternalErrorMiddleware"]
