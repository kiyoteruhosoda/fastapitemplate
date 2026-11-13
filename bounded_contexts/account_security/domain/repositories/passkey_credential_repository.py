"""Persistence interface for passkeys (implemented in Infrastructure)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.account_security.domain.entities.passkey_credential import (
    PasskeyCredential,
)


class PasskeyCredentialRepository(Protocol):
    def list_for_user(self, user_id: int) -> Sequence[PasskeyCredential]:
        """Return the passkeys registered by *user_id* in registration order."""

    def find_by_credential_id(self, credential_id: str) -> PasskeyCredential | None:
        """Look up a passkey by credential ID (used at authentication)."""

    def add(self, credential: PasskeyCredential) -> PasskeyCredential:
        """Register a passkey.

        Raises
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyAlreadyRegisteredError`
        if the same credential ID exists on **someone else's** account. Re-registration by the
        same user is treated as an overwrite.
        """

    def update_usage(self, credential: PasskeyCredential) -> PasskeyCredential:
        """Apply the signature counter and last-used time after a successful authentication."""

    def delete(self, user_id: int, passkey_id: int) -> None:
        """Delete a passkey owned by *user_id*. Raises
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyNotFoundError` if missing.
        """


__all__ = ["PasskeyCredentialRepository"]
