"""Interface for WebAuthn Relying Party operations (implemented in Infrastructure).

JSON exchanged with the browser is handled as plain ``dict``s, so the WebAuthn library's
types are not carried into the domain or application layers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PublicKeyOptions:
    """Options and challenge passed to the browser's ``navigator.credentials``."""

    public_key: dict[str, Any]
    challenge: str


@dataclass(frozen=True)
class VerifiedRegistration:
    """Result of verifying a registration response."""

    credential_id: str
    public_key: str
    sign_count: int
    attestation_format: str | None
    aaguid: str | None
    backup_eligible: bool
    backup_state: bool


@dataclass(frozen=True)
class VerifiedAssertion:
    """Result of verifying an authentication response."""

    credential_id: str
    sign_count: int


class WebAuthnRelyingParty(Protocol):
    def create_registration_options(
        self,
        *,
        user_id: int,
        user_name: str,
        display_name: str,
        exclude_credential_ids: Sequence[str] = (),
    ) -> PublicKeyOptions:
        """Build the options for passkey registration."""

    def verify_registration(self, *, credential: Mapping[str, Any], expected_challenge: str) -> VerifiedRegistration:
        """Verify a registration response. Raises
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyVerificationError` on failure.
        """

    def create_authentication_options(self, *, allow_credential_ids: Sequence[str] = ()) -> PublicKeyOptions:
        """Build the options for passkey authentication.

        If ``allow_credential_ids`` is empty, the authenticator picks the credential itself
        (login without entering a username).
        """

    def verify_authentication(
        self,
        *,
        credential: Mapping[str, Any],
        expected_challenge: str,
        stored_public_key: str,
        stored_sign_count: int,
    ) -> VerifiedAssertion:
        """Verify an authentication response. Raises
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyVerificationError` on failure.
        """

    def extract_credential_id(self, credential: Mapping[str, Any]) -> str | None:
        """Extract the credential ID from a response (to look up the stored key before verification)."""


__all__ = [
    "PublicKeyOptions",
    "VerifiedAssertion",
    "VerifiedRegistration",
    "WebAuthnRelyingParty",
]
