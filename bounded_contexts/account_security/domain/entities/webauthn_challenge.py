"""WebAuthn challenge (a one-time random value for registration/authentication).

The challenge is handed to the browser and checked against the signed one that comes back.
The issuing process and the verifying process may differ (Gunicorn runs multiple workers),
so it lives in the DB rather than process memory. Only ``challenge_id`` is returned to the
user; the challenge itself does not make the round trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Purpose. DB-native ENUMs are not used by policy, so allowed values are managed in Python
# (see "DB modeling" in CLAUDE.md).
CHALLENGE_PURPOSE_REGISTRATION = "registration"
CHALLENGE_PURPOSE_AUTHENTICATION = "authentication"
CHALLENGE_PURPOSES: tuple[str, ...] = (
    CHALLENGE_PURPOSE_REGISTRATION,
    CHALLENGE_PURPOSE_AUTHENTICATION,
)


@dataclass(frozen=True)
class WebAuthnChallenge:
    challenge_id: str
    challenge: str
    purpose: str
    expires_at: datetime
    user_id: int | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


__all__ = [
    "CHALLENGE_PURPOSES",
    "CHALLENGE_PURPOSE_AUTHENTICATION",
    "CHALLENGE_PURPOSE_REGISTRATION",
    "WebAuthnChallenge",
]
