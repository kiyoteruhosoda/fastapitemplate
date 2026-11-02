"""ログインごとの控え（``refresh_sessions``。ADR-0091）。

リフレッシュトークンの振り替えと、使い回しの見分けをここに集める。

- **今の 1 本**（``current_jti``）だけが新しいトークン対を受け取れる。ただし前の振り替えから
  :data:`REUSE_GRACE_SECONDS` が過ぎるまでは振り替えず、アクセストークンだけを受け取る（ADR-0092）
- **直前の 1 本**（``previous_jti``）は振り替えから :data:`REUSE_GRACE_SECONDS` のあいだだけ、
  アクセストークンだけを受け取れる。タブが同時に更新したときの負けた側で、Cookie は勝った側のものを残す
- **それ以外**は使い回し。そのログインだけを終わらせる（ほかの端末は巻き込まない）

寿命の決め方もここに集める（:func:`lifetime_for`。ADR-0101）。
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

#: 直前の 1 本を受け付ける長さ。ほかのタブの更新が同時に走る幅で足りる
REUSE_GRACE_SECONDS = 30


class RefreshStanding(StrEnum):
    CURRENT = "current"
    JUST_ROTATED = "just_rotated"
    REUSED = "reused"


@dataclass(frozen=True)
class RefreshLifetime:
    """これから出すトークンの寿命。``exp``・Cookie・控えを 1 つの値から揃える（ADR-0101）。

    設定は 1 回だけ読んでここへ固める。読むたびに値が変わると、途中で設定を変えたときに食い違う。
    """

    #: 終わる時刻（UTC naive・秒まで）。``exp`` は秒までしか持たないので、控えも秒に揃える
    expires_at: datetime
    #: 振り替えで控えの ``expires_at`` を書くか
    extends: bool
    #: Cookie の ``max_age``（秒）
    max_age: int


@dataclass(frozen=True)
class IssuedRefreshToken:
    """控えへ記録する 1 本。"""

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
    """次に出すトークンの寿命を決める。

    ``continued_session_id`` は寿命を受け継ぐログインの控えで、``None`` は新しいログイン。

    - 新しいログインと、延長ありの続き: 今から設定の期間
    - 延長なしの続き: 控えの ``expires_at`` のまま。設定の期間を変えても縮めない

    ⚠ **ここで読むのは寿命だけで、勝ち負けは決めない。** 同時に来た更新の勝者を決めるのは :func:`rotate` の条件である。
    延長なしでは ``expires_at`` を書かないので、読んだ値が古くなることもない。
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
    """ログインの始まりに 1 行置く。期限の切れた行はここで掃除する（定期実行を持たない）。"""
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
    """今の 1 本を ``issued`` へ振り替える。振り替えられなかったら偽。

    ⚠ **読んでから書かない。** 同時に来た更新のうち勝つのは 1 本だけで、それを決めるのはこの
    ``UPDATE`` の条件である。負けた側は Cookie を載せない（負けた側が後から載せると、捨てられた
    トークンが Cookie に残り、次の更新で使い回しに見える）。

    ⚠ **前の振り替えから猶予が過ぎるまでは振り替えない**（ADR-0092）。続けて振り替えると、まだ届いていない
    ほかのタブの更新が持つ 1 本が「直前」から外れ、使い回しに見えてログインが終わる。

    ``expected_jti`` が ``None`` なのはロールの切り替え（更新の Cookie が届かない口で、どの 1 本かを問わない）。

    延長なしなら ``expires_at`` に触らない（ADR-0101）。
    """
    conditions = [RefreshSession.id == issued.session_id]
    if expected_jti is not None:
        settled = utcnow() - timedelta(seconds=REUSE_GRACE_SECONDS)
        conditions.append(RefreshSession.current_jti == expected_jti)
        conditions.append(or_(RefreshSession.rotated_at.is_(None), RefreshSession.rotated_at < settled))
    # ⚠ **順番を固定する。** MariaDB は SET を左から評価する（標準 SQL と違う）。``values()`` は列の定義順に
    #   並べるので、current_jti が先だと previous_jti に新しい値が入り、直前の 1 本が使い回しに見える。
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
