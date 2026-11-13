"""Second-factor verification at login.

Handles only the check right after a successful password authentication; token issuance is
not involved (that is the Presentation layer's ``TokenService``).
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
    TotpRequiredError,
)
from bounded_contexts.account_security.domain.repositories.totp_secret_repository import (
    TotpSecretRepository,
)
from bounded_contexts.account_security.domain.services.totp_authenticator import (
    TotpAuthenticator,
)


@dataclass(frozen=True)
class VerifySecondFactor:
    repository: TotpSecretRepository
    authenticator: TotpAuthenticator

    def execute(self, *, user_id: int, code: str | None) -> None:
        """Verify *code* if two-factor authentication is enabled. Do nothing if it is not.

        An unconfirmed enrollment (shared key issued but not confirmed) is not "enabled".
        Requiring it here would lock out users who abandoned enrollment.
        """
        stored = self.repository.find_by_user(user_id)
        if stored is None or not stored.is_confirmed:
            return
        if not code:
            raise TotpRequiredError
        if not self.authenticator.verify(secret=stored.secret, code=code):
            raise InvalidTotpCodeError


__all__ = ["VerifySecondFactor"]
