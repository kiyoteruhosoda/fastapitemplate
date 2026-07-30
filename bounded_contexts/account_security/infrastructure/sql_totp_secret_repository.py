"""TOTP シークレットの SQLAlchemy 実装。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from bounded_contexts.account_security.domain.entities.totp_secret import TotpSecret
from bounded_contexts.account_security.domain.exceptions import TotpNotEnrolledError
from bounded_contexts.account_security.infrastructure.account_security_models import (
    TotpSecretRecord,
)


@dataclass(frozen=True)
class SqlTotpSecretRepository:
    session: Session

    def find_by_user(self, user_id: int) -> TotpSecret | None:
        record = self.session.get(TotpSecretRecord, user_id)
        return None if record is None else _to_entity(record)

    def save(self, secret: TotpSecret) -> TotpSecret:
        record = self.session.get(TotpSecretRecord, secret.user_id)
        if record is None:
            record = TotpSecretRecord(
                user_id=secret.user_id,
                secret=secret.secret,
                confirmed_at=secret.confirmed_at,
            )
            self.session.add(record)
        else:
            record.secret = secret.secret
            record.confirmed_at = secret.confirmed_at
        self.session.flush()
        return _to_entity(record)

    def confirm(self, user_id: int, confirmed_at: datetime) -> TotpSecret:
        record = self.session.get(TotpSecretRecord, user_id)
        if record is None:
            raise TotpNotEnrolledError
        record.confirmed_at = confirmed_at
        self.session.flush()
        return _to_entity(record)

    def delete(self, user_id: int) -> None:
        record = self.session.get(TotpSecretRecord, user_id)
        if record is not None:
            self.session.delete(record)
            self.session.flush()


def _to_entity(record: TotpSecretRecord) -> TotpSecret:
    return TotpSecret(user_id=record.user_id, secret=record.secret, confirmed_at=record.confirmed_at)


__all__ = ["SqlTotpSecretRepository"]
