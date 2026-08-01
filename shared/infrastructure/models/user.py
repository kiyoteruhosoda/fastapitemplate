"""ユーザー・パスワードリセットトークンのモデル。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base

user_roles = sa.Table(
    "user_roles",
    Base.metadata,
    sa.Column("user_id", BigIntPk, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("role_id", BigIntPk, sa.ForeignKey("roles.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True, server_default=sa.true())
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    roles = relationship("Role", secondary=user_roles, lazy="selectin")

    @property
    def permission_codes(self) -> frozenset[str]:
        """保有権限 = 全ロールが持つ権限の和集合。"""
        return frozenset(p.code for r in self.roles for p in r.permissions)

    @property
    def role_names(self) -> tuple[str, ...]:
        """付与されているロール名。切り替えの選択肢の提示に使う（認可には使わない）。"""
        return tuple(sorted(r.name for r in self.roles))

    def permission_codes_of(self, role_name: str | None) -> frozenset[str]:
        """アクティブロール 1 つ分の権限（ADR-0017）。

        ``role_name`` が ``None`` なら「すべてのロール」＝保有権限の和集合。
        付与されていないロール名は空集合になる（切り替えた後にそのロールを
        外されても、権限が残らないようにするため）。
        """
        if role_name is None:
            return self.permission_codes
        return frozenset(p.code for r in self.roles if r.name == role_name for p in r.permissions)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    expires_at = mapped_column(sa.DateTime(), nullable=False)
    used_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


__all__ = ["PasswordResetToken", "User", "user_roles"]
