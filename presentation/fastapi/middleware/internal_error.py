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
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from presentation.fastapi.error_handling import internal_error_response


class InternalErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as error:
            # 最後の受け皿なので、ここでは種類を問わず握って応答へ変える。
            return internal_error_response(request, error)


__all__ = ["InternalErrorMiddleware"]
