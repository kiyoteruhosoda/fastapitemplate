"""保持期間を過ぎた行の削除実装（``log`` と ``audit_log`` の両方）。

**リクエストのセッションとは別の短命コネクション**で書く。呼び出し元は常駐スレッド
でリクエストの外にいるため、既存のセッションに相乗りする先が無い。

**まとめて 1 回の DELETE にせず、主キーで小分けにする。** 溜まった行を初めて消す
ときは数十万行が対象になり得る。1 文で消すと MariaDB では該当行を掴んだまま長い
トランザクションになり、SQLite では DB 全体の書き込みロックをその間握り続ける。
どちらもリクエストの処理を待たせるので、1 回あたりの単位を区切って間に合間を作る。

``DELETE ... LIMIT`` はバックエンド依存（Python 同梱の SQLite では使えない）なので、
「消す ID を選ぶ → その ID を消す」の 2 段で行う。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

import sqlalchemy as sa

from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from shared.infrastructure.models.log import Log
from shared.kernel.database.db import get_engine

DEFAULT_CHUNK_SIZE = 1000


class SqlExpiredLogRemover:
    """*cutoff* より古い行を、主キーで小分けにしながら削除する。"""

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._chunk_size = chunk_size

    def delete_application_logs_before(self, cutoff: datetime) -> int:
        return _delete_in_chunks(
            sa.select(Log.id).where(Log.created_at < cutoff).order_by(Log.id),
            lambda ids: sa.delete(Log).where(Log.id.in_(ids)),
            self._chunk_size,
        )

    def delete_audit_logs_before(self, cutoff: datetime) -> int:
        return _delete_in_chunks(
            sa.select(AuditLogModel.id).where(AuditLogModel.occurred_at < cutoff).order_by(AuditLogModel.id),
            lambda ids: sa.delete(AuditLogModel).where(AuditLogModel.id.in_(ids)),
            self._chunk_size,
        )


def _delete_in_chunks(
    expired_ids: sa.Select[tuple[int]],
    delete_by_ids: Callable[[Sequence[int]], sa.Delete],
    chunk_size: int,
) -> int:
    """対象が尽きるまで *chunk_size* 件ずつ削除し、削除した総数を返す。

    1 塊ごとにトランザクションを閉じる。取得件数が *chunk_size* に満たなければ
    それが最後の塊（次を問い合わせずに終える）。
    """
    limited = expired_ids.limit(chunk_size)
    deleted = 0
    while True:
        with get_engine().begin() as connection:
            ids = list(connection.scalars(limited))
            if ids:
                connection.execute(delete_by_ids(ids))
        deleted += len(ids)
        if len(ids) < chunk_size:
            return deleted


__all__ = ["DEFAULT_CHUNK_SIZE", "SqlExpiredLogRemover"]
