"""Use case inputs/outputs (the shape returned to the Presentation layer)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TwoFactorStatusDto:
    """Two-factor authentication status.

    ``enrolling`` means "the shared key was issued but not yet confirmed in the authenticator app".
    """

    enabled: bool
    enrolling: bool


@dataclass(frozen=True)
class TotpEnrollmentDto:
    """What is handed to the user when enrollment starts.

    ``secret`` is for manual entry when the QR code can't be scanned by the authenticator app.
    """

    secret: str
    otpauth_uri: str


@dataclass(frozen=True)
class PasskeyChallengeDto:
    """WebAuthn options passed to the browser, and the ID sent back at verification."""

    challenge_id: str
    public_key: dict[str, Any]


@dataclass(frozen=True)
class PasskeySummaryDto:
    """For listing registered passkeys."""

    id: int
    name: str
    transports: tuple[str, ...]
    created_at: datetime | None
    last_used_at: datetime | None


__all__ = [
    "PasskeyChallengeDto",
    "PasskeySummaryDto",
    "TotpEnrollmentDto",
    "TwoFactorStatusDto",
]
