"""SQLAlchemy implementation of WebAuthn challenges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    WebAuthnChallenge,
)
from bounded_contexts.account_security.domain.exceptions import ChallengeNotFoundError
from bounded_contexts.account_security.infrastructure.account_security_models import (
    WebAuthnChallengeRecord,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class SqlWebAuthnChallengeRepository:
    session: Session

    def issue(self, challenge: WebAuthnChallenge) -> WebAuthnChallenge:
        # Expired ones would keep piling up if left alone, so clean up on every issuance.
        # The table doesn't bloat even without a dedicated periodic job.
        self.session.execute(delete(WebAuthnChallengeRecord).where(WebAuthnChallengeRecord.expires_at < utcnow()))
        self.session.add(
            WebAuthnChallengeRecord(
                challenge_id=challenge.challenge_id,
                challenge=challenge.challenge,
                purpose=challenge.purpose,
                user_id=challenge.user_id,
                expires_at=challenge.expires_at,
            )
        )
        self.session.flush()
        return challenge

    def consume(self, challenge_id: str, purpose: str) -> WebAuthnChallenge:
        record = self.session.get(WebAuthnChallengeRecord, challenge_id)
        if record is None or record.purpose != purpose:
            raise ChallengeNotFoundError

        challenge = WebAuthnChallenge(
            challenge_id=record.challenge_id,
            challenge=record.challenge,
            purpose=record.purpose,
            user_id=record.user_id,
            expires_at=record.expires_at,
        )

        # With "read, then delete", if the same assertion is sent twice concurrently, both may
        # finish reading before either delete commits, and both get a token. Consumption is
        # decided by **whether the delete succeeded** (one row deleted). DELETE takes a row lock,
        # so the later one waits for the earlier commit and then returns 0 rows.
        result = cast(
            "CursorResult[Any]",
            self.session.execute(
                delete(WebAuthnChallengeRecord).where(WebAuthnChallengeRecord.challenge_id == challenge_id),
                # Don't leave synchronization to the dialect; clean up the deleted row explicitly with expunge
                execution_options={"synchronize_session": False},
            ),
        )
        deleted = result.rowcount
        self.session.expunge(record)
        if deleted != 1:
            raise ChallengeNotFoundError

        # Delete even if expired (so that retries can't keep at it)
        if challenge.is_expired(utcnow()):
            raise ChallengeNotFoundError
        return challenge


__all__ = ["SqlWebAuthnChallengeRepository"]
