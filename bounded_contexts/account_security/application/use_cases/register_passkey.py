"""パスキーの登録（ログイン済みの利用者が自分の認証器を追加する）。"""

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
        """登録用オプションを発行する。

        登録済みの資格情報は ``excludeCredentials`` として渡し、同じ認証器を
        二重に登録させない（ブラウザ側で弾かれる）。
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
        # チャレンジは発行した本人の分だけ使える。ここを見ないと、A の
        # challenge_id を握った B が「A 向けに発行された資格情報」を B の
        # アカウントに保存でき、以後その資格情報で B としてログインできてしまう。
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
    """レスポンスの ``response.transports`` を取り出す（無ければ空）。"""
    response = credential.get("response")
    if not isinstance(response, Mapping):
        return ()
    transports = response.get("transports")
    if not isinstance(transports, (list, tuple)):
        return ()
    return tuple(value for value in transports if isinstance(value, str))


__all__ = ["CompletePasskeyRegistration", "StartPasskeyRegistration"]
