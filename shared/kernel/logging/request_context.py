"""リクエストコンテキスト（``requestId``・接続元・操作主体）の伝播。

ミドルウェアと認証依存関数が設定した値を ``contextvars`` で保持する。読み手は 2 つ。

- アプリログ: 全レコードへ自動付与する（``logging_config.RequestContextFilter``）。
- 監査ログ: リクエスト文脈として記録する（audit コンテキストの Presentation 層が
  ここから ``AuditRequestContext`` を組み立てる）。

引数で引き回さないのは、ログと監査がどちらも横断的関心事で、途中の全関数へ
リクエスト情報を通すと本来の責務が埋もれるため。
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_hash_var: ContextVar[str | None] = ContextVar("user_id_hash", default=None)
# 監査ログの「誰が」。認証依存関数が検証後に設定する（未認証のリクエストでは None）。
actor_user_id_var: ContextVar[int | None] = ContextVar("actor_user_id", default=None)
ip_address_var: ContextVar[str | None] = ContextVar("ip_address", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()


def current_user_id_hash() -> str | None:
    return user_id_hash_var.get()


def current_actor_user_id() -> int | None:
    return actor_user_id_var.get()


def current_ip_address() -> str | None:
    return ip_address_var.get()


def current_user_agent() -> str | None:
    return user_agent_var.get()


__all__ = [
    "actor_user_id_var",
    "current_actor_user_id",
    "current_ip_address",
    "current_request_id",
    "current_user_agent",
    "current_user_id_hash",
    "ip_address_var",
    "request_id_var",
    "user_agent_var",
    "user_id_hash_var",
]
