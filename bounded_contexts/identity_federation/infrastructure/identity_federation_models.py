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
    """コールバックが発行する 1 回限りの引き換え券（ハッシュのみ保存）。"""

    __tablename__ = "sso_login_tickets"

    ticket_hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    redirect_to: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


__all__ = [
    "FederatedIdentityRecord",
    "SsoLoginTicketRecord",
]
