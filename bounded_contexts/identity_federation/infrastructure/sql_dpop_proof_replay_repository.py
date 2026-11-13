"""SQLAlchemy implementation of ``DpopProofReplayRepository`` (ADR-0103).

⚠ **Decide with a single "insert unless duplicate" INSERT.** Check-then-insert in two steps lets both
through when the same proof arrives twice concurrently. Catching a primary key violation would roll back
the request's transaction too.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert

from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    DpopProofReplayRecord,
)
from shared.kernel.timestamps import to_naive_utc, utcnow


@dataclass(frozen=True)
class SqlDpopProofReplayRepository:
    session: Session

    def record_if_unused(self, replay_key: str, retain_until: datetime) -> bool:
        self.session.execute(delete(DpopProofReplayRecord).where(DpopProofReplayRecord.expires_at < utcnow()))
        values = {"replay_key": replay_key, "expires_at": to_naive_utc(retain_until)}
        result = cast(CursorResult[Any], self.session.execute(self._insert_unless_present().values(**values)))
        return result.rowcount == 1

    def _insert_unless_present(self) -> Insert:
        if self.session.get_bind().dialect.name == "sqlite":
            return sqlite.insert(DpopProofReplayRecord).on_conflict_do_nothing()
        # MariaDB / MySQL
        return mysql.insert(DpopProofReplayRecord).prefix_with("IGNORE")


__all__ = ["SqlDpopProofReplayRepository"]
