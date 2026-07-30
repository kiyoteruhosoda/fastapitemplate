"""パスキーの SQLAlchemy 実装。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.account_security.domain.entities.passkey_credential import (
    PasskeyCredential,
)
from bounded_contexts.account_security.domain.exceptions import (
    PasskeyAlreadyRegisteredError,
    PasskeyNotFoundError,
)
from bounded_contexts.account_security.infrastructure.account_security_models import (
    PasskeyCredentialRecord,
)


@dataclass(frozen=True)
class SqlPasskeyCredentialRepository:
    session: Session

    def list_for_user(self, user_id: int) -> Sequence[PasskeyCredential]:
        records = self.session.scalars(
            select(PasskeyCredentialRecord)
            .where(PasskeyCredentialRecord.user_id == user_id)
            .order_by(PasskeyCredentialRecord.created_at, PasskeyCredentialRecord.id)
        ).all()
        return [_to_entity(record) for record in records]

    def find_by_credential_id(self, credential_id: str) -> PasskeyCredential | None:
        record = self.session.scalar(
            select(PasskeyCredentialRecord).where(PasskeyCredentialRecord.credential_id == credential_id)
        )
        return None if record is None else _to_entity(record)

    def add(self, credential: PasskeyCredential) -> PasskeyCredential:
        existing = self.session.scalar(
            select(PasskeyCredentialRecord).where(PasskeyCredentialRecord.credential_id == credential.credential_id)
        )
        if existing is not None:
            if existing.user_id != credential.user_id:
                raise PasskeyAlreadyRegisteredError
            # 本人が同じ認証器を登録し直した場合は上書きする
            record = existing
        else:
            record = PasskeyCredentialRecord(user_id=credential.user_id, credential_id=credential.credential_id)
            self.session.add(record)

        record.public_key = credential.public_key
        record.sign_count = credential.sign_count
        record.transports = list(credential.transports)
        record.name = credential.name
        record.attestation_format = credential.attestation_format
        record.aaguid = credential.aaguid
        record.backup_eligible = credential.backup_eligible
        record.backup_state = credential.backup_state
        self.session.flush()
        return _to_entity(record)

    def update_usage(self, credential: PasskeyCredential) -> PasskeyCredential:
        record = self.session.scalar(
            select(PasskeyCredentialRecord).where(PasskeyCredentialRecord.credential_id == credential.credential_id)
        )
        if record is None:
            raise PasskeyNotFoundError
        record.sign_count = credential.sign_count
        record.last_used_at = credential.last_used_at
        self.session.flush()
        return _to_entity(record)

    def delete(self, user_id: int, passkey_id: int) -> None:
        record = self.session.get(PasskeyCredentialRecord, passkey_id)
        if record is None or record.user_id != user_id:
            # 他人のパスキーの存在を漏らさないため、権限違反も「存在しない」と扱う
            raise PasskeyNotFoundError
        self.session.delete(record)
        self.session.flush()


def _to_entity(record: PasskeyCredentialRecord) -> PasskeyCredential:
    transports = record.transports if isinstance(record.transports, list) else []
    return PasskeyCredential(
        id=record.id,
        user_id=record.user_id,
        credential_id=record.credential_id,
        public_key=record.public_key,
        sign_count=record.sign_count,
        transports=tuple(value for value in transports if isinstance(value, str)),
        name=record.name,
        attestation_format=record.attestation_format,
        aaguid=record.aaguid,
        backup_eligible=record.backup_eligible,
        backup_state=record.backup_state,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
    )


__all__ = ["SqlPasskeyCredentialRepository"]
