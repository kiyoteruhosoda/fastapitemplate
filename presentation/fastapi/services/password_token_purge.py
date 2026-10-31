"""期限切れ・使用済みのパスワード再設定トークンの掃除（ADR-0097）。

ログの掃除（ADR-0075 §3）と同じ常駐スレッドの作りで回す。ログと違って設定は持たない。
使えなくなった行を残す理由が無く、残すと発行の記録（誰がいつ再設定を頼んだか）が積もるだけである。
"""

from __future__ import annotations

import logging
from typing import Any, cast

import sqlalchemy as sa

from shared.infrastructure.models import PasswordResetToken
from shared.kernel.database.db import get_session_factory
from shared.kernel.scheduling import start_interval_worker
from shared.kernel.timestamps import utcnow

logger = logging.getLogger(__name__)

WORKER_NAME = "password-token-purge"
PURGE_INTERVAL_SECONDS = 6 * 60 * 60


def purge_spent_password_tokens_once() -> int:
    """使えなくなった行を消し、消した行数を返す。何度流しても同じ結果になる（複数のプロセスが流す）。"""
    spent = sa.or_(PasswordResetToken.used_at.is_not(None), PasswordResetToken.expires_at < utcnow())
    with get_session_factory()() as session:
        deleted = cast("sa.CursorResult[Any]", session.execute(sa.delete(PasswordResetToken).where(spent))).rowcount
        session.commit()
    if deleted:
        logger.info("password_tokens_purged", extra={"deleted_password_tokens": deleted})
    return deleted


def _purge() -> None:
    purge_spent_password_tokens_once()


def start_password_token_purge_worker() -> None:
    start_interval_worker(WORKER_NAME, _purge, PURGE_INTERVAL_SECONDS)


__all__ = [
    "PURGE_INTERVAL_SECONDS",
    "WORKER_NAME",
    "purge_spent_password_tokens_once",
    "start_password_token_purge_worker",
]
