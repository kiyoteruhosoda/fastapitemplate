"""ログインごとの控え（``refresh_sessions``。ADR-0091）。

リフレッシュトークンの振り替えと、使い回しの見分けをここに集める。

- **今の 1 本**（``current_jti``）だけが新しいトークン対を受け取れる。ただし前の振り替えから
  :data:`REUSE_GRACE_SECONDS` が過ぎるまでは振り替えず、アクセストークンだけを受け取る（ADR-0092）
- **直前の 1 本**（``previous_jti``）は振り替えから :data:`REUSE_GRACE_SECONDS` のあいだだけ、
  アクセストークンだけを受け取れる。タブが同時に更新したときの負けた側で、Cookie は勝った側のものを残す
- **それ以外**は使い回し。そのログインだけを終わらせる（ほかの端末は巻き込まない）
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, or_, update
from sqlalchemy.orm import Session

from shared.infrastructure.models import RefreshSession
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow

#: 直前の 1 本を受け付ける長さ。ほかのタブの更新が同時に走る幅で足りる
REUSE_GRACE_SECONDS = 30


class RefreshStanding(StrEnum):
    CURRENT = "current"
    JUST_ROTATED = "just_rotated"
    REUSED = "reused"


def new_identifier() -> str:
    return secrets.token_hex(16)


def standing_of(row: RefreshSession, jti: str) -> RefreshStanding:
    if jti == row.current_jti:
        return RefreshStanding.CURRENT
    grace = timedelta(seconds=REUSE_GRACE_SECONDS)
    if jti == row.previous_jti and row.rotated_at is not None and utcnow() - row.rotated_at <= grace:
        return RefreshStanding.JUST_ROTATED
    return RefreshStanding.REUSED


def _expires_at() -> datetime:
    return utcnow() + timedelta(seconds=settings.refresh_token_expires_seconds)


def begin(session: Session, *, session_id: str, user_id: int, jti: str) -> None:
    """ログインの始まりに 1 行置く。期限の切れた行はここで掃除する（定期実行を持たない）。"""
    session.execute(delete(RefreshSession).where(RefreshSession.expires_at < utcnow()))
    session.add(RefreshSession(id=session_id, user_id=user_id, current_jti=jti, expires_at=_expires_at()))
    session.flush()


def rotate(session: Session, *, session_id: str, new_jti: str, expected_jti: str | None = None) -> bool:
    """今の 1 本を ``new_jti`` へ振り替える。振り替えられなかったら偽。

    ⚠ **読んでから書かない。** 同時に来た更新のうち勝つのは 1 本だけで、それを決めるのはこの
    ``UPDATE`` の条件である。負けた側は Cookie を載せない（負けた側が後から載せると、捨てられた
    トークンが Cookie に残り、次の更新で使い回しに見える）。

    ⚠ **前の振り替えから猶予が過ぎるまでは振り替えない**（ADR-0092）。続けて振り替えると、まだ届いていない
    ほかのタブの更新が持つ 1 本が「直前」から外れ、使い回しに見えてログインが終わる。

    ``expected_jti`` が ``None`` なのはロールの切り替え（更新の Cookie が届かない口で、どの 1 本かを問わない）。
    """
    conditions = [RefreshSession.id == session_id]
    if expected_jti is not None:
        settled = utcnow() - timedelta(seconds=REUSE_GRACE_SECONDS)
        conditions.append(RefreshSession.current_jti == expected_jti)
        conditions.append(or_(RefreshSession.rotated_at.is_(None), RefreshSession.rotated_at < settled))
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(RefreshSession)
            .where(and_(*conditions))
            .values(
                previous_jti=RefreshSession.current_jti,
                current_jti=new_jti,
                rotated_at=utcnow(),
                expires_at=_expires_at(),
            ),
            execution_options={"synchronize_session": False},
        ),
    )
    return result.rowcount == 1


def end(session: Session, session_id: str) -> None:
    session.execute(delete(RefreshSession).where(RefreshSession.id == session_id))


__all__ = ["REUSE_GRACE_SECONDS", "RefreshStanding", "begin", "end", "new_identifier", "rotate", "standing_of"]
