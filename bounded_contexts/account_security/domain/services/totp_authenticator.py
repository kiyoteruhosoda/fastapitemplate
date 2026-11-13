"""Interface for generating and verifying TOTP (implemented in Infrastructure).

The RFC 6238 computation itself is left to a library. The domain only knows three things:
"create a shared key", "build the URI handed to the authenticator app" and "verify a code".
"""

from __future__ import annotations

from typing import Protocol


class TotpAuthenticator(Protocol):
    def generate_secret(self) -> str:
        """Issue a new shared key (Base32)."""

    def provisioning_uri(self, *, secret: str, account_name: str) -> str:
        """Build the ``otpauth://`` URI read by the authenticator app."""

    def verify(self, *, secret: str, code: str) -> bool:
        """Check whether a one-time code is correct (the clock-skew tolerance is set by the implementation)."""


__all__ = ["TotpAuthenticator"]
