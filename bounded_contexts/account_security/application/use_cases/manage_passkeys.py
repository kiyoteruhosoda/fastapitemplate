"""登録済みパスキーの一覧・削除。"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.account_security.application.dto.account_security_dto import (
    PasskeySummaryDto,
)
from bounded_contexts.account_security.domain.repositories.passkey_credential_repository import (
    PasskeyCredentialRepository,
)


@dataclass(frozen=True)
class ListPasskeys:
    repository: PasskeyCredentialRepository

    def execute(self, user_id: int) -> list[PasskeySummaryDto]:
        return [
            PasskeySummaryDto(
                id=credential.id or 0,
                name=credential.display_name,
                transports=credential.transports,
                created_at=credential.created_at,
                last_used_at=credential.last_used_at,
            )
            for credential in self.repository.list_for_user(user_id)
        ]


@dataclass(frozen=True)
class DeletePasskey:
    repository: PasskeyCredentialRepository

    def execute(self, *, user_id: int, passkey_id: int) -> None:
        self.repository.delete(user_id, passkey_id)


__all__ = ["DeletePasskey", "ListPasskeys"]
