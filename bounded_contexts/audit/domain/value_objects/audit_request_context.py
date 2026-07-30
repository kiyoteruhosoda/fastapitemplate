"""監査イベントに付随するリクエスト情報。

``request_id`` は ``log`` テーブルと同じ値を入れる。これにより「1 リクエストの
アプリログ」と「そのリクエストで起きた監査イベント」を突き合わせられる。
"""

from __future__ import annotations

from dataclasses import dataclass

# DDL と一致させる上限（超過分は保存前に切り詰める）
MAX_IP_ADDRESS_LENGTH = 45
MAX_USER_AGENT_LENGTH = 512
MAX_REQUEST_ID_LENGTH = 36


@dataclass(frozen=True)
class AuditRequestContext:
    """接続元と追跡キー。リクエスト外（スクリプト実行等）では全て ``None``。"""

    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    @classmethod
    def empty(cls) -> AuditRequestContext:
        """リクエスト文脈が無いときの値。"""
        return cls()


__all__ = [
    "MAX_IP_ADDRESS_LENGTH",
    "MAX_REQUEST_ID_LENGTH",
    "MAX_USER_AGENT_LENGTH",
    "AuditRequestContext",
]
