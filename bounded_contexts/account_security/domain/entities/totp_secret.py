"""TOTP secret (the shared key for time-based one-time passwords).

One per user. Two-factor authentication becomes "enabled" only once ``confirmed_at`` is set.
Enabling it midway through enrollment (just after showing the QR code) would lock out users
who failed to add it to their authenticator app, so it stays unconfirmed until the
confirmation code verifies successfully.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TotpSecret:
    user_id: int
    secret: str
    confirmed_at: datetime | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


__all__ = ["TotpSecret"]
