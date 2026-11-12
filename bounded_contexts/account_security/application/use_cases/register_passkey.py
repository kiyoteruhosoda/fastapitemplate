"""Passkey registration (a signed-in user adds their own authenticator)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from bounded_contexts.account_security.application.dto.account_security_dto import (
    PasskeyChallengeDto,
    PasskeySummaryDto,
)
from bounded_contexts.account_security.domain.entities.passkey_credential import (
    PasskeyCredential,
)
from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    CHALLENGE_PURPOSE_REGISTRATION,
    WebAuthnChallenge,
)
from bounded_contexts.account_security.domain.exceptions import ChallengeNotFoundError
from bounded_contexts.account_security.domain.repositories.passkey_credential_repository import (
    PasskeyCredentialRepository,
)
from bounded_contexts.account_security.domain.repositories.webauthn_challenge_repository import (
    WebAuthnChallengeRepository,
)
from bounded_contexts.account_security.domain.services.webauthn_relying_party import (
    WebAuthnRelyingParty,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class StartPasskeyRegistration:
    credentials: PasskeyCredentialRepository
    challenges: WebAuthnChallengeRepository
    relying_party: WebAuthnRelyingParty
    challenge_ttl_seconds: int

    def execute(self, *, user_id: int, user_name: str, display_name: str) -> PasskeyChallengeDto:
        """Issue the registration options.

        Already registered credentials are passed as ``excludeCredentials`` so the same
        authenticator can't be registered twice (the browser rejects it).
        """
        registered = self.credentials.list_for_user(user_id)
        options = self.relying_party.create_registration_options(
            user_id=user_id,
            user_name=user_name,
            display_name=display_name,
            exclude_credential_ids=[item.credential_id for item in registered],
        )
        challenge_id = uuid.uuid4().hex
        self.challenges.issue(
            WebAuthnChallenge(
                challenge_id=challenge_id,
                challenge=options.challenge,
                purpose=CHALLENGE_PURPOSE_REGISTRATION,
                user_id=user_id,
                expires_at=utcnow() + timedelta(seconds=self.challenge_ttl_seconds),
            )
        )
        return PasskeyChallengeDto(challenge_id=challenge_id, public_key=options.public_key)


@dataclass(frozen=True)
class CompletePasskeyRegistration:
    credentials: PasskeyCredentialRepository
    challenges: WebAuthnChallengeRepository
    relying_party: WebAuthnRelyingParty

    def execute(
        self,
        *,
        user_id: int,
        challenge_id: str,
        credential: Mapping[str, Any],
        name: str | None = None,
    ) -> PasskeySummaryDto:
        challenge = self.challenges.consume(challenge_id, CHALLENGE_PURPOSE_REGISTRATION)
        # A challenge can only be used by the user it was issued to. Without this check, B holding
        # A's challenge_id could save "the credential issued for A" to B's account, and from then
        # on log in as B with that credential.
        if challenge.user_id != user_id:
            raise ChallengeNotFoundError

        verified = self.relying_party.verify_registration(credential=credential, expected_challenge=challenge.challenge)
        stored = self.credentials.add(
            PasskeyCredential(
                user_id=user_id,
                credential_id=verified.credential_id,
                public_key=verified.public_key,
                sign_count=verified.sign_count,
                transports=_extract_transports(credential),
                name=(name or "").strip() or None,
                attestation_format=verified.attestation_format,
                aaguid=verified.aaguid,
                backup_eligible=verified.backup_eligible,
                backup_state=verified.backup_state,
            )
        )
        return PasskeySummaryDto(
            id=stored.id or 0,
            name=stored.display_name,
            transports=stored.transports,
            created_at=stored.created_at,
            last_used_at=stored.last_used_at,
        )


def _extract_transports(credential: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract ``response.transports`` from the response (empty if absent)."""
    response = credential.get("response")
    if not isinstance(response, Mapping):
        return ()
    transports = response.get("transports")
    if not isinstance(transports, (list, tuple)):
        return ()
    return tuple(value for value in transports if isinstance(value, str))


__all__ = ["CompletePasskeyRegistration", "StartPasskeyRegistration"]
