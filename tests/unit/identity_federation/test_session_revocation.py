"""停止の記録が、どのトークンを無効にするか（ADR-0036）。"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    """⚠ 止めたあとにログインし直した利用者を巻き添えにしない。

    比べるのは**マイクロ秒まで持つ開始時刻**で、トークンの ``iat``（秒まで）ではない。
    """
    assert not _revocation("session-1").covers(_login(started_at=_NOW + timedelta(microseconds=1)))


def test_another_session_of_the_same_user_survives() -> None:
    """``sid`` まで分かっているなら、その端末だけを落とす。"""
    assert not _revocation("session-1").covers(_login("session-2"))


def test_a_stop_without_a_sid_reaches_every_session() -> None:
    assert _revocation(None).covers(_login("session-2"))


def test_another_user_is_never_touched() -> None:
    assert not _revocation(None).covers(_login(subject="someone-else"))


def test_the_record_is_kept_only_as_long_as_a_token_can_live() -> None:
    """リフレッシュトークンの寿命を過ぎれば、記録より前のトークンは自力で切れる。"""
    assert _revocation(None).expires_at == _NOW + timedelta(seconds=3600)
