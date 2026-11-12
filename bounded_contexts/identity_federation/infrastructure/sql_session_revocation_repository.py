"""SQLAlchemy implementation of logout records (ADR-0077 §3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    FederatedSessionRevocationRecord,
)
from shared.infrastructure.models import RefreshSession
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class SqlSessionRevocationRepository:
    session: Session

    def record(self, revocation: SessionRevocation) -> bool:
        """Store the record. If the same ``jti`` already exists, ``False`` (ignored as a resend)."""
        self.session.execute(
            delete(FederatedSessionRevocationRecord).where(FederatedSessionRevocationRecord.expires_at < utcnow())
        )
        if self.session.get(FederatedSessionRevocationRecord, revocation.jti) is not None:
            return False
        self.session.add(
            FederatedSessionRevocationRecord(
                jti=revocation.jti,
                issuer=revocation.session.issuer,
                subject=revocation.session.subject,
                session_id=revocation.session.session_id,
                revoked_at=revocation.revoked_at,
                expires_at=self._kept_until(revocation.expires_at),
            )
        )
        self.session.flush()
        return True

    def _kept_until(self, earliest: datetime) -> datetime:
        """Time until which to keep the record. Never delete before the last of the current logins ends (ADR-0102).

        ⚠ **Don't filter by user.** Login records hold no IdP-side address, and bindings may have been removed.
        """
        last_end: datetime | None = self.session.scalar(select(func.max(RefreshSession.expires_at)))
        return earliest if last_end is None else max(earliest, last_end)

    def is_revoked(self, login: FederatedLogin) -> bool:
        """Whether there is a record invalidating that login.

        ⚠ **Rows with NULL ``session_id`` are per-user stops**, so they match whatever our
        ``session_id`` is. Conversely, when ours is ``None`` (an IdP that doesn't provide
        ``sid``), only per-user rows match.
        """
        record = FederatedSessionRevocationRecord
        target = login.session
        matches_session: ColumnElement[bool] = record.session_id.is_(None)
        if target.session_id is not None:
            matches_session = or_(matches_session, record.session_id == target.session_id)
        found = self.session.scalar(
            select(record.jti)
            .where(
                record.issuer == target.issuer,
                record.subject == target.subject,
                record.revoked_at >= login.started_at,
                matches_session,
            )
            .limit(1)
        )
        return found is not None


__all__ = ["SqlSessionRevocationRepository"]
