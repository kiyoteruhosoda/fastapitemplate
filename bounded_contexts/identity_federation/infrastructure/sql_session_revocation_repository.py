"""停止の記録の SQLAlchemy 実装（ADR-0036）。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, or_, select
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
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class SqlSessionRevocationRepository:
    session: Session

    def record(self, revocation: SessionRevocation) -> bool:
        """記録を残す。既に同じ ``jti`` があれば ``False``（再送として無視する）。"""
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
                expires_at=revocation.expires_at,
            )
        )
        self.session.flush()
        return True

    def is_revoked(self, login: FederatedLogin) -> bool:
        """そのログインを無効にする記録があるか。

        ⚠ **``session_id`` が NULL の行は利用者単位の停止**なので、こちらの
        ``session_id`` が何であっても当たる。逆に、こちらが ``None``（``sid`` を
        出さない IdP）のときは利用者単位の行にしか当たらない。
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
