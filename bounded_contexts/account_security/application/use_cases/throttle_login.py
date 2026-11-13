"""Count login failures per submitted identifier and refuse for a while past the limit (ADR-0076 §9).

Three steps: **before trying**, :meth:`require_allowed`; **when there was an attempt to count**,
:meth:`record_attempt`; **when it succeeds**, :meth:`record_success`.

The unit counted is the submitted identifier, regardless of whether it exists. Counting only
existing ones would reveal whether an account exists by whether it gets refused.
"""

from __future__ import annotations

from datetime import datetime

from bounded_contexts.account_security.domain.entities.login_attempts import (
    LoginAttempts,
    ThrottlePolicy,
)
from bounded_contexts.account_security.domain.exceptions import TooManyAttemptsError
from bounded_contexts.account_security.domain.repositories.login_attempt_repository import (
    LoginAttemptRepository,
)


def normalize_identifier(identifier: str) -> str:
    """Keep case and surrounding whitespace from making it a different identifier."""
    return identifier.strip().lower()


class ThrottleLogin:
    def __init__(self, repository: LoginAttemptRepository, policy: ThrottlePolicy) -> None:
        self._repository = repository
        self._policy = policy

    def require_allowed(self, purpose: str, identifier: str, now: datetime) -> None:
        """Raises :class:`TooManyAttemptsError` while refusing."""
        if not self._policy.enabled:
            return
        retry_after = self._load(purpose, identifier).retry_after(now)
        if retry_after is not None:
            raise TooManyAttemptsError(retry_after_seconds=max(int(retry_after.total_seconds()), 1))

    def record_attempt(self, purpose: str, identifier: str, now: datetime) -> bool:
        """Count one attempt. ``True`` **if this attempt started the lockout** (to record it in the audit log).

        Login counts failures; reset requests count successes too (a success still sends an email
        to the recipient, so not counting them would let someone flood the inbox).
        """
        if not self._policy.enabled:
            return False
        before = self._load(purpose, identifier)
        after = before.after_failure(now, self._policy)
        self._repository.save(after, now, self._policy)
        return after.locked_until is not None and before.retry_after(now) is None

    def record_success(self, purpose: str, identifier: str) -> None:
        """Entered correctly. Earlier failures were typos, so forget them."""
        if not self._policy.enabled:
            return
        self._repository.forget(purpose, normalize_identifier(identifier))

    def _load(self, purpose: str, identifier: str) -> LoginAttempts:
        return self._repository.get(purpose, normalize_identifier(identifier))


__all__ = ["ThrottleLogin", "normalize_identifier"]
