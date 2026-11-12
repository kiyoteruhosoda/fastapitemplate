"""Login with a passkey (passwordless authentication).

So that it can start without entering a username, ``allowCredentials`` is left empty and the
authenticator picks the credential (discoverable credential). Whose passkey it is gets determined
from the returned credential ID.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from bounded_contexts.account_security.application.dto.account_security_dto import (
    PasskeyChallengeDto,
)
from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    CHALLENGE_PURPOSE_AUTHENTICATION,
    WebAuthnChallenge,
)
from bounded_contexts.account_security.domain.exceptions import (
    PasskeyVerificationError,
)
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
class StartPasskeyAuthentication:
    challenges: WebAuthnChallengeRepository
    relying_party: WebAuthnRelyingParty
    challenge_ttl_seconds: int

    def execute(self) -> PasskeyChallengeDto:
        options = self.relying_party.create_authentication_options()
        challenge_id = uuid.uuid4().hex
        self.challenges.issue(
            WebAuthnChallenge(
                challenge_id=challenge_id,
                challenge=options.challenge,
                purpose=CHALLENGE_PURPOSE_AUTHENTICATION,
                expires_at=utcnow() + timedelta(seconds=self.challenge_ttl_seconds),
            )
        )
        return PasskeyChallengeDto(challenge_id=challenge_id, public_key=options.public_key)


@dataclass(frozen=True)
class CompletePasskeyAuthentication:
    credentials: PasskeyCredentialRepository
    challenges: WebAuthnChallengeRepository
    relying_party: WebAuthnRelyingParty

    def execute(self, *, challenge_id: str, credential: Mapping[str, Any]) -> int:
        """Return the owner (``user_id``) of the passkey that verified successfully."""
        challenge = self.challenges.consume(challenge_id, CHALLENGE_PURPOSE_AUTHENTICATION)

        credential_id = self.relying_party.extract_credential_id(credential)
        stored = self.credentials.find_by_credential_id(credential_id) if credential_id else None
        if stored is None:
            # Callers don't need to tell "unregistered credential" from "signature mismatch"
            # (both return the same response as a failed login).
            raise PasskeyVerificationError

        verified = self.relying_party.verify_authentication(
            credential=credential,
            expected_challenge=challenge.challenge,
            stored_public_key=stored.public_key,
            stored_sign_count=stored.sign_count,
        )
        self.credentials.update_usage(stored.with_usage(sign_count=verified.sign_count, used_at=utcnow()))
        return stored.user_id


__all__ = ["CompletePasskeyAuthentication", "StartPasskeyAuthentication"]
