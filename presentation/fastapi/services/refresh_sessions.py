"""Per-login records (``refresh_sessions``; ADR-0091).

Refresh token rotation and reuse detection live here.

- Only **the current token** (``current_jti``) can receive a new token pair. But until
  :data:`REUSE_GRACE_SECONDS` have passed since the last rotation, it is not rotated and receives
  only an access token (ADR-0092)
- **The previous token** (``previous_jti``) can receive only an access token, and only for
  :data:`REUSE_GRACE_SECONDS` after rotation. It is the loser when tabs refresh at once; the
  winner's cookie is kept
- **Anything else** is reuse. Only that login is ended (other devices are not affected)

Deciding the lifetime lives here too (:func:`lifetime_for`; ADR-0101).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, or_, select, update
from sqlalchemy.orm import Session

from shared.infrastructure.models import RefreshSession
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow

#: How long the previous token is accepted. Covering concurrent refreshes from other tabs is enough
REUSE_GRACE_SECONDS = 30


class RefreshStanding(StrEnum):
    CURRENT = "current"
    JUST_ROTATED = "just_rotated"
    REUSED = "reused"


@dataclass(frozen=True)
class RefreshLifetime:
    """Lifetime of the token about to be issued. ``exp``, cookie and record all derive from one value
    (ADR-0101).

    The setting is read once and fixed here. Reading it each time could disagree if the setting
    changed midway.
    """

    #: Expiry time (naive UTC, to the second). ``exp`` only has seconds, so the record matches
    expires_at: datetime
    #: Whether rotation writes the record's ``expires_at``
    extends: bool
    #: Cookie ``max_age`` (seconds)
    max_age: int


@dataclass(frozen=True)
class IssuedRefreshToken:
    """The token recorded in the login record."""

    session_id: str
    jti: str
    lifetime: RefreshLifetime


def new_identifier() -> str:
    return secrets.token_hex(16)


def standing_of(row: RefreshSession, jti: str) -> RefreshStanding:
    if jti == row.current_jti:
        return RefreshStanding.CURRENT
    grace = timedelta(seconds=REUSE_GRACE_SECONDS)
    if jti == row.previous_jti and row.rotated_at is not None and utcnow() - row.rotated_at <= grace:
        return RefreshStanding.JUST_ROTATED
    return RefreshStanding.REUSED


def has_expired(row: RefreshSession) -> bool:
    return bool(row.expires_at <= utcnow())


def lifetime_for(session: Session, continued_session_id: str | None) -> RefreshLifetime:
    """Decide the lifetime of the next token.

    ``continued_session_id`` is the login record whose lifetime is inherited; ``None`` is a new
    login.

    - New login, or continuation with sliding: the configured period from now
    - Continuation without sliding: the record's ``expires_at`` as is. Changing the configured
      period doesn't shorten it

    ⚠ **This only reads the lifetime; it doesn't pick a winner.** The winner among concurrent
    refreshes is decided by the condition in :func:`rotate`.
    Without sliding ``expires_at`` is never written, so the value read can't go stale.
    """
    now = utcnow()
    period = settings.refresh_token_expires_seconds
    if continued_session_id is not None and not settings.refresh_token_sliding_enabled:
        kept = session.scalar(select(RefreshSession.expires_at).where(RefreshSession.id == continued_session_id))
        if kept is not None:
            kept = kept.replace(microsecond=0)
            return RefreshLifetime(expires_at=kept, extends=False, max_age=max(0, int((kept - now).total_seconds())))
    return RefreshLifetime(
        expires_at=(now + timedelta(seconds=period)).replace(microsecond=0),
        extends=True,
        max_age=period,
    )


def begin(session: Session, *, issued: IssuedRefreshToken, user_id: int) -> None:
    """Insert one row at the start of a login. Expired rows are purged here (there is no periodic
    job)."""
    session.execute(delete(RefreshSession).where(RefreshSession.expires_at < utcnow()))
    session.add(
        RefreshSession(
            id=issued.session_id,
            user_id=user_id,
            current_jti=issued.jti,
            expires_at=issued.lifetime.expires_at,
        )
    )
    session.flush()


def rotate(session: Session, *, issued: IssuedRefreshToken, expected_jti: str | None = None) -> bool:
    """Rotate the current token to ``issued``. False if it could not be rotated.

    ⚠ **No read-then-write.** Only one of concurrent refreshes wins, and the condition of this
    ``UPDATE`` decides which. The losers don't set the cookie (if a loser set it afterwards, the
    discarded token would stay in the cookie and look like reuse on the next refresh).

    ⚠ **No rotation until the grace period since the last rotation has passed** (ADR-0092).
    Rotating twice in a row would push the token held by another tab's not-yet-arrived refresh out
    of "previous", making it look like reuse and ending the login.

    ``expected_jti`` is ``None`` for a role switch (an endpoint the refresh cookie doesn't reach,
    so any token is accepted).

    Without sliding, ``expires_at`` is not touched (ADR-0101).
    """
    conditions = [RefreshSession.id == issued.session_id]
    if expected_jti is not None:
        settled = utcnow() - timedelta(seconds=REUSE_GRACE_SECONDS)
        conditions.append(RefreshSession.current_jti == expected_jti)
        conditions.append(or_(RefreshSession.rotated_at.is_(None), RefreshSession.rotated_at < settled))
    # ⚠ **Fix the order.** MariaDB evaluates SET left to right (unlike standard SQL). ``values()``
    #   orders by column definition, so with current_jti first, previous_jti would get the new
    #   value and the previous token would look like reuse.
    assignments: list[tuple[Any, Any]] = [
        (RefreshSession.previous_jti, RefreshSession.current_jti),
        (RefreshSession.current_jti, issued.jti),
        (RefreshSession.rotated_at, utcnow()),
    ]
    if issued.lifetime.extends:
        assignments.append((RefreshSession.expires_at, issued.lifetime.expires_at))
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(RefreshSession).where(and_(*conditions)).ordered_values(*assignments),
            execution_options={"synchronize_session": False},
        ),
    )
    return result.rowcount == 1


def end(session: Session, session_id: str) -> None:
    session.execute(delete(RefreshSession).where(RefreshSession.id == session_id))


__all__ = [
    "REUSE_GRACE_SECONDS",
    "IssuedRefreshToken",
    "RefreshLifetime",
    "RefreshStanding",
    "begin",
    "end",
    "has_expired",
    "lifetime_for",
    "new_identifier",
    "rotate",
    "standing_of",
]
