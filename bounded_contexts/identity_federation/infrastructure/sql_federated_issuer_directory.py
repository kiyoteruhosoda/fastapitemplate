"""結び付きの棚卸しの SQLAlchemy 実装（ADR-0039）。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    FederatedIdentityRecord,
)


@dataclass(frozen=True)
class SqlFederatedIssuerDirectory:
    session: Session

    def issuers_by_user(self) -> dict[int, tuple[str, ...]]:
        rows = self.session.execute(
            select(FederatedIdentityRecord.user_id, FederatedIdentityRecord.issuer).order_by(
                FederatedIdentityRecord.issuer
            )
        ).all()
        grouped: dict[int, list[str]] = defaultdict(list)
        for user_id, issuer in rows:
            grouped[user_id].append(issuer)
        return {user_id: tuple(issuers) for user_id, issuers in grouped.items()}


__all__ = ["SqlFederatedIssuerDirectory"]
