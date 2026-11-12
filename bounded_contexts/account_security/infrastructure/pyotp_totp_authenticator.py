"""TOTP implementation (``pyotp``)."""

from __future__ import annotations

from dataclasses import dataclass

import pyotp


@dataclass(frozen=True)
class PyotpTotpAuthenticator:
    """Handles RFC 6238 TOTP with ``pyotp``.

    ``valid_window`` is how many time steps (30 seconds) before/after are accepted. Defaults to 1
    to absorb clock skew between the device and the server.
    """

    issuer: str
    valid_window: int = 1

    def generate_secret(self) -> str:
        return pyotp.random_base32()

    def provisioning_uri(self, *, secret: str, account_name: str) -> str:
        return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=self.issuer)

    def verify(self, *, secret: str, code: str) -> bool:
        normalised = code.strip().replace(" ", "")
        if not normalised.isdigit():
            return False
        return pyotp.TOTP(secret).verify(normalised, valid_window=self.valid_window)


__all__ = ["PyotpTotpAuthenticator"]
