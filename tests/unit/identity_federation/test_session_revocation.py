"""Which tokens a revocation record invalidates (ADR-0077 §3 / ADR-0077 §7)."""

from __future__ import annotations

from datetime import datetime, timedelta

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import (
    LogoutNotice,
)

_ISSUER = "https://idp.example.test"
_NOW = datetime(2026, 9, 14, 12, 0, 0)


def _revocation(session_id: str | None) -> SessionRevocation:
    notice = LogoutNotice(
        jti="delivery-1",
        session=FederatedSession(issuer=_ISSUER, subject="idp-subject", session_id=session_id),
    )
    return SessionRevocation.of(notice, now=_NOW, keep_for_seconds=3600)


def _login(
    session_id: str | None = "session-1",
    *,
    subject: str = "idp-subject",
    started_at: datetime = _NOW - timedelta(minutes=5),
) -> FederatedLogin:
    return FederatedLogin(
        session=FederatedSession(issuer=_ISSUER, subject=subject, session_id=session_id),
        started_at=started_at,
    )


def test_sessions_started_before_the_stop_are_dead() -> None:
    assert _revocation("session-1").covers(_login())


def test_sessions_started_after_the_stop_survive() -> None:
    """⚠ Do not drag in users who signed in again after the stop.

    What is compared is **the start time with microsecond precision**, not the token's ``iat`` (seconds).
    """
    assert not _revocation("session-1").covers(_login(started_at=_NOW + timedelta(microseconds=1)))


def test_another_session_of_the_same_user_survives() -> None:
    """If ``sid`` is known, only that device is signed out."""
    assert not _revocation("session-1").covers(_login("session-2"))


def test_a_stop_without_a_sid_reaches_every_session() -> None:
    assert _revocation(None).covers(_login("session-2"))


def test_another_user_is_never_touched() -> None:
    assert not _revocation(None).covers(_login(subject="someone-else"))


def test_the_record_is_kept_only_as_long_as_a_token_can_live() -> None:
    """After the refresh-token lifetime, tokens older than the record expire on their own."""
    assert _revocation(None).expires_at == _NOW + timedelta(seconds=3600)


# --- Revocations written by periodic reconciliation (ADR-0077 §7) -----------------------------------------


def _reconciled(last_login_at: datetime | None, *, subject: str = "idp-subject") -> SessionRevocation:
    identity = FederatedIdentity(issuer=_ISSUER, subject=subject, user_id=1, last_login_at=last_login_at)
    return SessionRevocation.after_reconciliation(identity, now=_NOW, keep_for_seconds=3600)


def test_reconciliation_ends_every_session_that_started_before_it() -> None:
    revocation = _reconciled(_NOW - timedelta(days=1))

    assert revocation.session.session_id is None
    assert revocation.covers(_login("any-session"))
    assert not revocation.covers(_login(started_at=_NOW + timedelta(seconds=1)))


def test_reconciliation_writes_the_same_jti_for_the_same_login() -> None:
    """⚠ Even running hourly, once per worker, it takes only one row."""
    logged_in = _NOW - timedelta(days=1)

    assert _reconciled(logged_in).jti == _reconciled(logged_in).jti


def test_reconciliation_writes_a_new_jti_after_a_new_login() -> None:
    """⚠ With the same ``jti``, a stop after the user came back and signed in again would be missed."""
    assert _reconciled(_NOW - timedelta(days=1)).jti != _reconciled(_NOW - timedelta(hours=1)).jti


def test_reconciliation_jti_fits_the_column_and_differs_per_subject() -> None:
    revocation = _reconciled(None)

    assert len(revocation.jti) == 64
    assert revocation.jti != _reconciled(None, subject="someone-else").jti
