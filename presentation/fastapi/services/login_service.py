"""Login credential verification (password -> two-factor auth -> audit record).

It is split out of the router because login is not just "take input, return a token". There is
matching, second-factor verification, classifying failure reasons, and an audit record for each;
in the router, business branching would mix with HTTP concerns.

**Every failure returns the same ``invalid_credentials``** (so account existence is not leaked).
Where it failed is recorded only in the audit log ``reason``.
"""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from bounded_contexts.account_security.application.use_cases.throttle_login import ThrottleLogin
from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.domain.entities.login_attempts import PURPOSE_LOGIN
from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
    TooManyAttemptsError,
    TotpRequiredError,
)
from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from presentation.fastapi.schemas.auth import LoginRequest
from shared.domain.auth import master_data
from shared.infrastructure.models import User
from shared.infrastructure.sign_in_directory import account_signing_in
from shared.kernel.settings.secret_guard import PRODUCTION
from shared.kernel.timestamps import utcnow
from shared.kernel.version import load_build_info

#: Hash used to equalize matching time for unknown identifiers. **Matches nothing**
#: (prevents existence being inferred from response time; ADR-0076 §9)
_DUMMY_HASH = generate_password_hash("no-account-has-this-password")


@dataclass(frozen=True)
class LoginChecks:
    """Checks run **before and after** the credentials. Bundled to keep the argument count within
    the design limit."""

    second_factor: VerifySecondFactor
    throttle: ThrottleLogin


class LoginService:
    def __init__(self, db: Session, checks: LoginChecks, audit: RecordAuditEvent) -> None:
        self._db = db
        self._second_factor = checks.second_factor
        self._throttle = checks.throttle
        self._audit = audit

    def authenticate(self, credentials: LoginRequest) -> User:
        """Verify credentials and return the user if they pass. Otherwise raise 401.

        For accounts with two-factor auth, ``totp_code`` is verified too. A missing code returns
        ``totp_required``, a mismatch ``invalid_totp`` (both mean the password was correct, so
        logging in again with the code is enough).

        Failures are counted per identifier; once the limit is hit, requests are refused with 429
        for a while (ADR-0076 §9).
        """
        self._require_not_locked(credentials.email)
        user = account_signing_in(self._db, credentials.email, credentials.tenant)
        if user is None:
            # Equalize matching time for unknown identifiers so response time reveals nothing
            check_password_hash(_DUMMY_HASH, credentials.password)
            self._reject(None, "unknown_email", credentials.email)
        if not user.is_active:
            self._reject(user, "inactive_user", credentials.email)
        if user.password_hash is None:
            # A user without a password entrance (ADR-0076 §6). There is nothing to match
            # against, so reject here.
            self._reject(user, "no_local_password", credentials.email)
        if not check_password_hash(user.password_hash, credentials.password):
            self._reject(user, "invalid_password", credentials.email)
        if _is_published_default(credentials.password):
            self._reject(user, "default_password", credentials.email)

        self._verify_second_factor(user, credentials)
        # Signed in correctly. Earlier failures were typos, so forget them
        self._throttle.record_success(PURPOSE_LOGIN, credentials.email)
        # Record which entrance was used (ADR-0076 §3 decision 1). Auth strength differs per
        # entrance, and without a record you can't later notice "suspended at the IdP but still
        # getting in".
        self._audit.as_actor(user.id).execute(AuditEventType.LOGIN_SUCCEEDED, reason="method=password")
        return user

    def _require_not_locked(self, identifier: str) -> None:
        """If currently refusing, 429 before matching (ADR-0076 §9).

        Refused attempts are audited too: an attack is visible precisely while refusing.
        The account hasn't been looked up yet, so the target is empty.
        """
        try:
            self._throttle.require_allowed(PURPOSE_LOGIN, identifier, utcnow())
        except TooManyAttemptsError:
            self._audit.execute(AuditEventType.LOGIN_FAILED, AuditResult.FAILURE, reason="locked")
            raise

    def _verify_second_factor(self, user: User, credentials: LoginRequest) -> None:
        """Verify the second-factor code. **Mistakes count toward the same tally as passwords**
        (ADR-0076 §9)."""
        try:
            self._second_factor.execute(user_id=user.id, code=credentials.totp_code)
        except (TotpRequiredError, InvalidTotpCodeError) as error:
            self._record_failure(user, error.code, credentials.email)
            # Normalize to 401 as an authentication failure (the default mapping gives 400)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": error.code},
            ) from None

    def _reject(self, user: User | None, reason: str, identifier: str) -> NoReturn:
        """Record the failure and return the same 401 regardless of reason.

        The return type is ``NoReturn`` so callers narrow ``user`` from ``User | None`` to
        ``User``.
        """
        self._record_failure(user, reason, identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    def _record_failure(self, user: User | None, reason: str, identifier: str) -> None:
        """Record the account as the **target, not the actor**.

        When authentication fails, "who tried" is unknown; recording the owner as actor would
        read as if the owner did it themselves (ADR-0075 §1).

        Failures are counted per identifier, and reaching the limit and starting to refuse is
        recorded too (ADR-0076 §9).
        """
        target = AuditTarget.of(AuditTargetType.USER, user.id) if user is not None else None
        self._audit.execute(AuditEventType.LOGIN_FAILED, AuditResult.FAILURE, target=target, reason=reason)
        if self._throttle.record_attempt(PURPOSE_LOGIN, identifier, utcnow()):
            self._audit.execute(AuditEventType.LOGIN_LOCKED, AuditResult.FAILURE, target=target, reason=reason)


def _is_published_default(password: str) -> bool:
    """Whether someone in production is signing in with the public default password (ADR-0073 §4).

    If ``ADMIN_INITIAL_PASSWORD`` is not provided, the default admin sits with full rights and the
    password published in the repository. **In production that value cannot sign in**, so a
    forgotten setting fails as "nobody can get in" rather than "anyone can". Development still
    allows it as before.
    """
    if load_build_info().environment != PRODUCTION:
        return False
    return compare_digest(password.encode(), master_data.DEFAULT_ADMIN_PASSWORD.encode())


__all__ = ["LoginChecks", "LoginService"]
