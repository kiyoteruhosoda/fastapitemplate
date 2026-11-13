"""Persistence interface for WebAuthn challenges (implemented in Infrastructure)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    WebAuthnChallenge,
)


class WebAuthnChallengeRepository(Protocol):
    def issue(self, challenge: WebAuthnChallenge) -> WebAuthnChallenge:
        """Save a challenge. Expired ones are cleaned up at the same time."""

    def consume(self, challenge_id: str, purpose: str) -> WebAuthnChallenge:
        """Take out a challenge and discard it (one-time).

        Raises :class:`~bounded_contexts.account_security.domain.exceptions.ChallengeNotFoundError`
        if it is not found, has a different purpose, or has expired.
        """


__all__ = ["WebAuthnChallengeRepository"]
