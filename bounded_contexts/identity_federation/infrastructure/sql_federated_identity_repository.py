"""SQLAlchemy implementation of IdP account bindings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    FederatedIdentityRecord,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class SqlFederatedIdentityRepository:
    session: Session

    def find(self, issuer: str, subject: str) -> FederatedIdentity | None:
        return _as_identity(self.session.get(FederatedIdentityRecord, (issuer, subject)))

    def find_for_user(self, issuer: str, user_id: int) -> FederatedIdentity | None:
        """⚠ Returns the first one, assuming **one binding per user per IdP**.

        The table has no user-side uniqueness constraint (so one person can have multiple IdPs),
        so preventing two bindings to the same IdP is the job of :class:`LinkFederatedIdentity`.
        """
        record = self.session.scalars(
            select(FederatedIdentityRecord)
            .where(FederatedIdentityRecord.issuer == issuer)
            .where(FederatedIdentityRecord.user_id == user_id)
            .order_by(FederatedIdentityRecord.created_at)
            .limit(1)
        ).first()
        return _as_identity(record)

    def is_linked(self, user_id: int) -> bool:
        """Whether bound to any IdP (name and email are owned by the IdP. ADR-0094)."""
        linked = select(FederatedIdentityRecord.user_id).where(FederatedIdentityRecord.user_id == user_id).limit(1)
        return self.session.scalar(linked) is not None

    def unlink(self, identity: FederatedIdentity) -> None:
        record = self.session.get(FederatedIdentityRecord, (identity.issuer, identity.subject))
        if record is None:
            return
        self.session.delete(record)
        self.session.flush()

    def link(self, identity: FederatedIdentity) -> FederatedIdentity:
        self.session.add(
            FederatedIdentityRecord(
                issuer=identity.issuer,
                subject=identity.subject,
                user_id=identity.user_id,
                last_login_at=utcnow(),
            )
        )
        self.session.flush()
        return identity

    def touch(self, identity: FederatedIdentity) -> None:
        record = self.session.get(FederatedIdentityRecord, (identity.issuer, identity.subject))
        if record is None:
            return
        record.last_login_at = utcnow()
        self.session.flush()

    def list_for_issuer(self, issuer: str) -> Sequence[FederatedIdentity]:
        """All users bound to that IdP (periodic reconciliation. ADR-0077 §7).

        Ordered by ``subject`` ascending, fixed. If the order varied with the query plan,
        matching against the records would look different each time.
        """
        records = self.session.scalars(
            select(FederatedIdentityRecord)
            .where(FederatedIdentityRecord.issuer == issuer)
            .order_by(FederatedIdentityRecord.subject)
        ).all()
        return [identity for identity in (_as_identity(record) for record in records) if identity is not None]


def _as_identity(record: FederatedIdentityRecord | None) -> FederatedIdentity | None:
    if record is None:
        return None
    return FederatedIdentity(
        issuer=record.issuer,
        subject=record.subject,
        user_id=record.user_id,
        linked_at=record.created_at,
        last_login_at=record.last_login_at,
    )


__all__ = ["SqlFederatedIdentityRepository"]
