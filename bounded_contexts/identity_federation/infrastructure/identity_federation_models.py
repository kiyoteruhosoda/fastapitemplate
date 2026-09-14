"""ID 連携コンテキストの SQLAlchemy モデル。

``migrations/env.py`` と ``tests/conftest.py`` がこのモジュールを import して
メタデータへ登録する（コンテキスト固有モデルの扱い。CLAUDE.md「DDL 管理」）。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base


class FederatedIdentityRecord(Base):
    """外部 IdP のアカウントと利用者の結び付き。

    鍵は ``(issuer, subject)``。利用者側には一意制約を置かない（1 人が複数の
    IdP アカウントを持てる）。
    """

    __tablename__ = "federated_identities"

    issuer: Mapped[str] = mapped_column(sa.String(255), primary_key=True)
    subject: Mapped[str] = mapped_column(sa.String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    last_login_at = mapped_column(sa.DateTime(), nullable=True)


class SsoLoginTicketRecord(Base):
    """コールバックが発行する 1 回限りの引き換え券（ハッシュのみ保存）。

    IdP 側のセッション（``issuer`` / ``subject`` / ``session_id``）も一緒に運ぶ。
    停止の伝播はこの 3 つ組を宛名にして届くので、**券を発行する時点で控えておかないと
    後から結び付けられない**（ADR-0036）。
    """

    __tablename__ = "sso_login_tickets"

    ticket_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    redirect_to: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    issuer: Mapped[str] = mapped_column(sa.String(255), nullable=False, default="")
    subject: Mapped[str] = mapped_column(sa.String(255), nullable=False, default="")
    #: ID トークンの ``sid``。出さない IdP があるので NULL 可。
    session_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    #: セッションが始まった時刻。停止の記録はこの時刻と突き合わせる（ADR-0036）。
    session_started_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


class FederatedSessionRevocationRecord(Base):
    """IdP から届いた「このセッションを止めろ」の記録（ADR-0036）。

    主キーが ``jti`` なのは、再送を**行の重複としてそのまま弾く**ため
    （ADR-0024 の送り手は再送でも同じ ``jti`` を使う）。
    ``session_id`` が NULL の行は、その利用者のすべてのセッションに効く。
    """

    __tablename__ = "federated_session_revocations"
    __table_args__ = (sa.Index("ix_federated_session_revocations_subject", "issuer", "subject"),)

    jti: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    issuer: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    subject: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    session_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    revoked_at = mapped_column(sa.DateTime(), nullable=False)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)


__all__ = [
    "FederatedIdentityRecord",
    "FederatedSessionRevocationRecord",
    "SsoLoginTicketRecord",
]
