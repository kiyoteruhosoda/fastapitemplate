"""リクエスト単位の構造化ログ（``requestId`` の採番と伝播）。

採番した ``requestId`` はレスポンスヘッダー（``X-Request-Id``）にも載せる。
アプリログ（``log``）と監査ログ（``audit_log``）の双方に同じ値が入るため、
利用者から受け取った ID で「そのリクエストで何が起きたか」を両側から追える。

接続元（IP・User-Agent）も併せて伝播する。監査ログが記録する値であり、
ハンドラの引数として引き回すと全ルーターに波及するため
（:mod:`shared.kernel.logging.request_context`）。
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shared.kernel.logging.request_context import (
    actor_user_id_var,
    ip_address_var,
    request_id_var,
    user_agent_var,
    user_id_hash_var,
)
from shared.kernel.settings.settings import settings

access_logger = logging.getLogger("app.request")

_FORWARDED_FOR_HEADER = "x-forwarded-for"


def _client_ip(request: Request) -> str | None:
    """接続元 IP を返す。監査ログに残る値なので、詐称できる経路を作らない。

    ``X-Forwarded-For`` は**送信元が自由に付けられるヘッダー**で、同梱の nginx が
    使う ``$proxy_add_x_forwarded_for`` は受け取った値の後ろに実際の接続元を足す。
    左端を採ると ``X-Forwarded-For: 1.2.3.4`` を送るだけで任意の IP を記録させられる。

    そこで信頼するのは ``TRUSTED_PROXY_HOPS`` で宣言した段数だけとし、右から数えて
    その位置の値を採る（プロキシが自分で足した値 = 詐称できない）。既定は 0 で、
    ヘッダーを一切見ずに TCP の接続元を使う。
    """
    client_host = request.client.host if request.client else None

    hops = settings.trusted_proxy_hops
    if hops <= 0:
        return client_host

    forwarded = request.headers.get(_FORWARDED_FOR_HEADER)
    if not forwarded:
        return client_host
    addresses = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(addresses) < hops:
        # 宣言した段数に足りない = 想定した経路を通っていない。ヘッダーを信じない。
        return client_host
    return addresses[-hops]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        # 前のリクエストの値が残らないよう、リクエストごとに明示的に初期化する
        user_id_hash_var.set(None)
        actor_user_id_var.set(None)
        ip_address_var.set(_client_ip(request))
        user_agent_var.set(request.headers.get("user-agent"))
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        access_logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-Id"] = request_id
        return response


__all__ = ["RequestLoggingMiddleware"]
