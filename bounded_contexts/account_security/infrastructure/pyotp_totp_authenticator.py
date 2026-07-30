"""TOTP の実装（``pyotp``）。"""

from __future__ import annotations

from dataclasses import dataclass

import pyotp


@dataclass(frozen=True)
class PyotpTotpAuthenticator:
    """RFC 6238 の TOTP を ``pyotp`` で扱う。

    ``valid_window`` は前後いくつの時間枠（30 秒）を許容するか。端末とサーバーの
    時計のずれを吸収するために既定で 1 を取る。
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
