"""Purge of expired or used password reset tokens (ADR-0097).

Runs on the same kind of background thread as the log purge (ADR-0075 §3). Unlike logs, it has
no settings: there is no reason to keep unusable rows, and keeping them only piles up a record of
issuance (who asked for a reset and when).
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
    """Delete unusable rows and return the count deleted. Idempotent (several processes run it)."""
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
