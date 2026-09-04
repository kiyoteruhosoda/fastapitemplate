"""IdP アカウントとの結び付きの SQLAlchemy 実装。"""

from __future__ import annotations

from dataclasses import dataclass

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
        record = self.session.get(FederatedIdentityRecord, (issuer, subject))
        if record is None:
            return None
        return FederatedIdentity(issuer=record.issuer, subject=record.subject, user_id=record.user_id)

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


__all__ = ["SqlFederatedIdentityRepository"]
