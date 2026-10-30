"""ユーザー・パスワードリセットトークンのモデル。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.domain.auth.authority import within_the_seat
from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared, tenancy_info
from shared.infrastructure.models.tenant import UserTenant
from shared.kernel.database.db import Base

user_roles = sa.Table(
    "user_roles",
    Base.metadata,
    sa.Column("user_id", BigIntPk, sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("role_id", BigIntPk, sa.ForeignKey("roles.id"), primary_key=True),
    info=tenancy_info(Tenancy.PERSONAL),
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    #: 一意なのは同じ席の中だけ（同じテナント、またはテナントの外。ADR-0079 §4）。引くときは
    #: ``shared.infrastructure.sign_in_directory`` を通す。
    email: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    username: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    #: ⚠ **NULL は「ローカルのパスワードが無い」**（ADR-0076 §6）。「空のパスワード」でも
    #: 「誰も知らない値が入っている」でもない。判定は :attr:`has_local_password` を通す。
    password_hash: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True, server_default=sa.true())
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    roles = relationship("Role", secondary=user_roles, lazy="selectin")
    #: ログインの区切り（ADR-0076 §8）。無ければ区切り無し。触れたときだけ引く。
    session_boundary: Mapped[UserSessionBoundary | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    #: 所属するテナント（ADR-0079 §1）。無いのはシステム管理者だけ。
    #: ⚠ **触れたときだけ引く（``selectin`` にしない）。** 据え付けの移行 ``0002`` がこのモデルで
    #: ``users`` を引く時点では ``user_tenants`` がまだ無いので、一緒に引くとそこで落ちる。
    membership: Mapped[UserTenant | None] = relationship(cascade="all, delete-orphan", uselist=False)

    @property
    def tenant_id(self) -> int | None:
        """所属するテナント。``None`` はテナントに属さない（システム管理者）。"""
        return self.membership.tenant_id if self.membership is not None else None

    def join(self, tenant_id: int) -> None:
        """テナントに入れる。利用者はちょうど 1 つのテナントに属する（付け替えはしない）。"""
        if self.membership is not None and self.membership.tenant_id != tenant_id:
            raise ValueError("a user belongs to exactly one tenant")
        if self.membership is None:
            self.membership = UserTenant(tenant_id=tenant_id)

    def end_sessions(self) -> None:
        """いまより前に始まったログインを、次の更新で全部終わらせる（ADR-0076 §8）。

        パスワードを変えた・再設定した・管理者が付け直したときに呼ぶ。止まるのは
        更新とトークンの出し直しで、手元のアクセストークンは寿命（既定 5 分）まで
        通る（ADR-0076 §5）。
        """
        if self.session_boundary is None:
            self.session_boundary = UserSessionBoundary(valid_from=utcnow())
        else:
            self.session_boundary.valid_from = utcnow()

    @property
    def sessions_valid_from(self) -> datetime | None:
        """この時刻より前に出したトークンでは更新させない。``None`` は区切り無し（ADR-0076 §8）。"""
        return self.session_boundary.valid_from if self.session_boundary is not None else None

    @property
    def has_local_password(self) -> bool:
        """パスワードでこのアプリへ入れるか（ADR-0076 §6）。

        ⚠ **偽を「まだ決めていない」と読まないこと。** 偽は「この利用者に
        パスワードという入り口は無い」であり、リセットでも生やさない。持たせるのは
        管理者が明示的にパスワードを設定したときだけ。
        """
        return self.password_hash is not None

    @property
    def permission_codes(self) -> frozenset[str]:
        """保有権限 = 全ロールが持つ権限の和集合。"""
        return frozenset(p.code for r in self.roles for p in r.permissions)

    @property
    def role_names(self) -> tuple[str, ...]:
        """付与されているロール名。切り替えの選択肢の提示に使う（認可には使わない）。"""
        return tuple(sorted(r.name for r in self.roles))

    def permission_codes_of(self, role_name: str | None) -> frozenset[str]:
        """アクティブロール 1 つ分の権限（ADR-0078 §1）。

        ``role_name`` が ``None`` なら「すべてのロール」＝保有権限の和集合。
        付与されていないロール名は空集合になる（切り替えた後にそのロールを
        外されても、権限が残らないようにするため）。

        座る場所（テナントの中か外か）で効かない権限は落とす（ADR-0079 §1。兼ねない）。
        """
        if role_name is None:
            granted = self.permission_codes
        else:
            granted = frozenset(p.code for r in self.roles if r.name == role_name for p in r.permissions)
        return within_the_seat(self.tenant_id is not None, granted)


class UserSessionBoundary(Base):
    """ログインの区切り（ADR-0076 §8）。1 人 1 行。

    **これより前に出したトークンでは更新・出し直しをさせない。** サーバーにセッションの
    控えが無いので、パスワードを変えたときに前のログインを終わらせる手段はこれだけ。

    ⚠ **``users`` の列にしない。** 古い移行（据え付けの ``0002``）がこのモデルで
    ``users`` を書くので、列を足すと「列を足す移行」より前の段で落ちる。
    """

    __tablename__ = "user_session_boundaries"
    __table_args__ = declared(Tenancy.PERSONAL)

    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    valid_from = mapped_column(sa.DateTime(), nullable=False)

    user: Mapped[User] = relationship(back_populates="session_boundary")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    #: ``reset``（本人の申し込み）か ``invitation``（管理者の招待。最初のパスワードを決めさせる。ADR-0079 §5）
    purpose: Mapped[str] = mapped_column(
        sa.Enum("reset", "invitation", name="password_token_purpose", native_enum=False),
        nullable=False,
        default="reset",
        server_default="reset",
    )
    expires_at = mapped_column(sa.DateTime(), nullable=False)
    used_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


__all__ = ["PasswordResetToken", "User", "UserSessionBoundary", "user_roles"]
