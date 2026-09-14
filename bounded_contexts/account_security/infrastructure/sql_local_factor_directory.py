"""第二要素の棚卸しの SQLAlchemy 実装（ADR-0039）。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bounded_contexts.account_security.domain.value_objects.local_factors import (
    LocalFactors,
)
from bounded_contexts.account_security.infrastructure.account_security_models import (
    PasskeyCredentialRecord,
    TotpSecretRecord,
)


@dataclass(frozen=True)
class SqlLocalFactorDirectory:
    session: Session

    def factors_by_user(self) -> dict[int, LocalFactors]:
        """2 本のクエリで全員分を集める（利用者ごとに引かない）。"""
        confirmed = set(
            self.session.scalars(
                select(TotpSecretRecord.user_id).where(TotpSecretRecord.confirmed_at.is_not(None))
            ).all()
        )
        counted = self.session.execute(
            select(PasskeyCredentialRecord.user_id, func.count())
            .select_from(PasskeyCredentialRecord)
            .group_by(PasskeyCredentialRecord.user_id)
        ).all()
        passkeys: dict[int, int] = {}
        for user_id, passkey_count in counted:
            passkeys[user_id] = passkey_count
        return {
            user_id: LocalFactors(totp=user_id in confirmed, passkeys=passkeys.get(user_id, 0))
            for user_id in confirmed | set(passkeys)
        }


__all__ = ["SqlLocalFactorDirectory"]
