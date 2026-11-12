"""SQLAlchemy implementation of the failure records.

⚠ **Does not use the request's session.** Recording a failure goes back together with a 401 —
i.e. it exits via an exception, so anything written to the request's session is lost on rollback.
For the same reason the audit log is written outside the request (ADR-0075 §1), this **opens a
short session per operation and commits it**.

It doesn't clash with SQLite's write lock because, when it is called, the request's session has
not written anything yet (it is called before credential matching / before a reset request).
Changing that order would make this block.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session, sessionmaker

from bounded_contexts.account_security.domain.entities.login_attempts import (
    LoginAttempts,
    ThrottlePolicy,
)
from bounded_contexts.account_security.infrastructure.account_security_models import (
    LoginAttemptRecord,
)


@dataclass(frozen=True)
class SqlLoginAttemptRepository:
    session_factory: sessionmaker[Session]

    def get(self, purpose: str, identifier: str) -> LoginAttempts:
        with self.session_factory() as session:
            record = session.get(LoginAttemptRecord, (purpose, identifier))
            if record is None:
                return LoginAttempts(purpose=purpose, identifier=identifier)
            return LoginAttempts(
                purpose=record.purpose,
                identifier=record.identifier,
                failures=record.failures,
                window_started_at=record.window_started_at,
                locked_until=record.locked_until,
            )

    def save(self, attempts: LoginAttempts, now: datetime, policy: ThrottlePolicy) -> None:
        with self.session_factory() as session:
            # Rows for unknown identifiers pile up (they are counted so as not to leak existence),
            # so each write cleans up "rows past both the window and the lockout". No dedicated job
            _sweep(session, now, policy)
            record = session.get(LoginAttemptRecord, (attempts.purpose, attempts.identifier))
            if record is None:
                record = LoginAttemptRecord(purpose=attempts.purpose, identifier=attempts.identifier)
                session.add(record)
            record.failures = attempts.failures
            record.window_started_at = attempts.window_started_at
            record.locked_until = attempts.locked_until
            session.commit()

    def forget(self, purpose: str, identifier: str) -> None:
        with self.session_factory() as session:
            session.execute(
                delete(LoginAttemptRecord).where(
                    LoginAttemptRecord.purpose == purpose,
                    LoginAttemptRecord.identifier == identifier,
                )
            )
            session.commit()


def _sweep(session: Session, now: datetime, policy: ThrottlePolicy) -> None:
    stale_window = now - policy.window
    session.execute(
        delete(LoginAttemptRecord).where(
            or_(LoginAttemptRecord.locked_until.is_(None), LoginAttemptRecord.locked_until <= now),
            or_(
                LoginAttemptRecord.window_started_at.is_(None),
                LoginAttemptRecord.window_started_at <= stale_window,
            ),
        )
    )


__all__ = ["SqlLoginAttemptRepository"]
