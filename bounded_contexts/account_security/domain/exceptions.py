"""Domain exceptions of the account security context.

The Presentation layer maps these to an HTTP status + error code
(the frontend turns them into display text; see "Internationalization" in CLAUDE.md).
"""

from __future__ import annotations


class AccountSecurityError(Exception):
    """Base exception of this context. ``code`` becomes the API error code as is."""

    code = "account_security_error"


class TotpAlreadyEnabledError(AccountSecurityError):
    """Tried to start enrollment on an account that already has two-factor authentication enabled."""

    code = "totp_already_enabled"


class TotpNotEnrolledError(AccountSecurityError):
    """Enrollment has not been started (nothing to verify the confirmation code against)."""

    code = "totp_not_enrolled"


class InvalidTotpCodeError(AccountSecurityError):
    """The confirmation code does not match."""

    code = "invalid_totp"


class TotpRequiredError(AccountSecurityError):
    """Two-factor authentication is enabled but no code was presented."""

    code = "totp_required"


class ChallengeNotFoundError(AccountSecurityError):
    """WebAuthn challenge not found (expired, already used, or another process)."""

    code = "challenge_not_found"


class PasskeyVerificationError(AccountSecurityError):
    """WebAuthn signature verification failed."""

    code = "passkey_verification_failed"


class PasskeyAlreadyRegisteredError(AccountSecurityError):
    """The same credential is already registered to another account."""

    code = "passkey_already_registered"


class PasskeyNotFoundError(AccountSecurityError):
    """The specified passkey does not exist (including ones belonging to someone else)."""

    code = "passkey_not_found"


class TooManyAttemptsError(AccountSecurityError):
    """Too many failures in a short time, so refuse for a while (ADR-0076 §9).

    Don't blend this into ``401``. If people can't tell they are being refused, they keep being
    rejected even with the correct password, assume they "forgot" it, and go to reset it.
    """

    code = "too_many_attempts"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"retry after {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


__all__ = [
    "AccountSecurityError",
    "ChallengeNotFoundError",
    "InvalidTotpCodeError",
    "PasskeyAlreadyRegisteredError",
    "PasskeyNotFoundError",
    "PasskeyVerificationError",
    "TooManyAttemptsError",
    "TotpAlreadyEnabledError",
    "TotpNotEnrolledError",
    "TotpRequiredError",
]
