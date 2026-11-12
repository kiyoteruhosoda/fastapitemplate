"""Passkey (WebAuthn credential).

``sign_count`` is the signature counter held by the authenticator. It increases monotonically
on every authentication, so a rollback hints that the credential was cloned. The verification
itself is done by the WebAuthn library; this just takes the verified new value and advances.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class PasskeyCredential:
    user_id: int
    credential_id: str
    public_key: str
    sign_count: int = 0
    transports: tuple[str, ...] = ()
    name: str | None = None
    attestation_format: str | None = None
    aaguid: str | None = None
    backup_eligible: bool = False
    backup_state: bool = False
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    # None before persistence, as no ID has been assigned yet
    id: int | None = None

    def with_usage(self, *, sign_count: int, used_at: datetime) -> PasskeyCredential:
        """Return the state after a successful authentication."""
        return replace(self, sign_count=sign_count, last_used_at=used_at)

    @property
    def display_name(self) -> str:
        """Name the user identifies it by (the start of the credential ID if not set)."""
        return self.name or f"passkey-{self.credential_id[:8]}"


__all__ = ["PasskeyCredential"]
