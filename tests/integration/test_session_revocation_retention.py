"""How long revocation records are kept (ADR-0102)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.domain.entities.federated_identity import FederatedIdentity
from bounded_contexts.identity_federation.domain.entities.session_revocation import SessionRevocation
from bounded_contexts.identity_federation.domain.value_objects.federated_session import FederatedSession
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import LogoutNotice
from bounded_contexts.identity_federation.infrastructure import sql_session_revocation_repository
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    FederatedSessionRevocationRecord,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from shared.infrastructure.models import RefreshSession, User

_ISSUER = "https://identity.example.test/tenant"
_NOW = datetime(2026, 11, 2, 12, 0, 0)
_PERIOD_SECONDS = 60


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sql_session_revocation_repository, "utcnow", lambda: _NOW)


def _login_ending_at(session: Session, name: str, ends_at: datetime) -> None:
    user = User(email=f"{name}@example.com", username=name, password_hash="local-password", is_active=True)
    session.add(user)
    session.flush()
    session.add(RefreshSession(id=f"rsid-{name}", user_id=user.id, current_jti=f"jti-{name}", expires_at=ends_at))
    session.flush()


def _stop(session: Session, jti: str) -> datetime:
    notice = LogoutNotice(jti=jti, session=FederatedSession(_ISSUER, "sub-1", "sid-1"))
    revocation = SessionRevocation.of(notice, now=_NOW, keep_for_seconds=_PERIOD_SECONDS)
    assert SqlSessionRevocationRepository(session).record(revocation) is True
    return _kept_until(session, jti)


def _kept_until(session: Session, jti: str) -> datetime:
    record = session.get(FederatedSessionRevocationRecord, jti)
    assert record is not None
    kept_until: datetime = record.expires_at
    return kept_until


def test_a_stop_is_kept_until_the_last_login_ends(db_session: Session) -> None:
    last_end = _NOW + timedelta(hours=1)
    _login_ending_at(db_session, "alice", _NOW + timedelta(minutes=30))
    _login_ending_at(db_session, "bob", last_end)

    assert _stop(db_session, "delivery-1") == last_end


def test_a_stop_is_kept_for_the_period_when_every_login_ends_sooner(db_session: Session) -> None:
    _login_ending_at(db_session, "alice", _NOW + timedelta(seconds=10))

    assert _stop(db_session, "delivery-1") == _NOW + timedelta(seconds=_PERIOD_SECONDS)


def test_a_stop_is_kept_for_the_period_when_nobody_is_signed_in(db_session: Session) -> None:
    assert _stop(db_session, "delivery-1") == _NOW + timedelta(seconds=_PERIOD_SECONDS)


def test_a_stop_found_by_reconciliation_is_kept_the_same_way(db_session: Session) -> None:
    last_end = _NOW + timedelta(hours=1)
    _login_ending_at(db_session, "alice", last_end)
    identity = FederatedIdentity(user_id=1, issuer=_ISSUER, subject="sub-1", last_login_at=_NOW)
    revocation = SessionRevocation.after_reconciliation(identity, now=_NOW, keep_for_seconds=_PERIOD_SECONDS)

    assert SqlSessionRevocationRepository(db_session).record(revocation) is True

    assert _kept_until(db_session, revocation.jti) == last_end


def test_a_stop_is_swept_after_the_last_login_ended(db_session: Session) -> None:
    _login_ending_at(db_session, "alice", _NOW - timedelta(seconds=1))
    db_session.add(
        FederatedSessionRevocationRecord(
            jti="old",
            issuer=_ISSUER,
            subject="sub-1",
            session_id=None,
            revoked_at=_NOW - timedelta(hours=2),
            expires_at=_NOW - timedelta(seconds=1),
        )
    )
    db_session.flush()

    _stop(db_session, "delivery-1")

    assert db_session.get(FederatedSessionRevocationRecord, "old") is None
