"""保持期間を過ぎた行の削除インターフェース（実装は Infrastructure 層）。

検索（``ApplicationLogQuery`` / ``AuditLogQuery``）とは別のインターフェースにする。
読み取りはリクエストのセッションで行うが、削除は独立したトランザクションで小分けに
実行するもので、寿命も呼び出し元も違うため（ADR-0021）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ExpiredLogRemover(Protocol):
    def delete_application_logs_before(self, cutoff: datetime) -> int:
        """*cutoff* より古いアプリログを削除し、削除した行数を返す。"""

    def delete_audit_logs_before(self, cutoff: datetime) -> int:
        """*cutoff* より古い監査ログを削除し、削除した行数を返す。"""


__all__ = ["ExpiredLogRemover"]
