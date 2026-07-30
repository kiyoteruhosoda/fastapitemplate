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

access_logger = logging.getLogger("app.request")

# X-Forwarded-For は "client, proxy1, proxy2" の並び。最初の要素が本来の接続元。
_FORWARDED_FOR_HEADER = "x-forwarded-for"


def _client_ip(request: Request) -> str | None:
    """接続元 IP を返す。リバースプロキシ配下では転送ヘッダーを優先する。"""
    forwarded = request.headers.get(_FORWARDED_FOR_HEADER)
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else None


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
