"""Models for users and password reset tokens."""

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
    #: Unique only within the same seat (the same tenant, or outside the tenants; ADR-0079 §4).
    #: Look users up through ``shared.infrastructure.sign_in_directory``.
    email: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    username: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    #: ⚠ **NULL means "no local password"** (ADR-0076 §6). It is neither "an empty password" nor
    #: "a value nobody knows". Check it through :attr:`has_local_password`.
    password_hash: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True, server_default=sa.true())
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    roles = relationship("Role", secondary=user_roles, lazy="selectin")
    #: Sign-in boundary (ADR-0076 §8). None means no boundary. Loaded only when accessed.
    session_boundary: Mapped[UserSessionBoundary | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    #: The tenant the user belongs to (ADR-0079 §1). Only system administrators have none.
    #: ⚠ **Loaded only when accessed (not ``selectin``).** When the setup migration ``0002`` loads
    #: ``users`` through this model, ``user_tenants`` does not exist yet, so eager loading fails there.
    membership: Mapped[UserTenant | None] = relationship(cascade="all, delete-orphan", uselist=False)

    @property
    def tenant_id(self) -> int | None:
        """The tenant the user belongs to. ``None`` means no tenant (system administrator)."""
        return self.membership.tenant_id if self.membership is not None else None

    def join(self, tenant_id: int) -> None:
        """Put the user in a tenant. A user belongs to exactly one tenant (never moved)."""
        if self.membership is not None and self.membership.tenant_id != tenant_id:
            raise ValueError("a user belongs to exactly one tenant")
        if self.membership is None:
            self.membership = UserTenant(tenant_id=tenant_id)

    def end_sessions(self) -> None:
        """End every sign-in that started before now, at its next refresh (ADR-0076 §8).

        Call this when the password was changed, reset, or re-set by an administrator. What stops
        is refreshing and reissuing tokens; access tokens already held stay valid until they
        expire (default 5 minutes; ADR-0076 §5).
        """
        if self.session_boundary is None:
            self.session_boundary = UserSessionBoundary(valid_from=utcnow())
        else:
            self.session_boundary.valid_from = utcnow()

    @property
    def sessions_valid_from(self) -> datetime | None:
        """Tokens issued before this time cannot refresh. ``None`` means no boundary (ADR-0076 §8)."""
        return self.session_boundary.valid_from if self.session_boundary is not None else None

    @property
    def has_local_password(self) -> bool:
        """Whether the user can sign in to this app with a password (ADR-0076 §6).

        ⚠ **Do not read false as "not decided yet".** False means "this user has no password
        entrance", and a reset does not create one. One is given only when an administrator
        explicitly sets a password.
        """
        return self.password_hash is not None

    @property
    def permission_codes(self) -> frozenset[str]:
        """Held permissions = union of the permissions of all roles."""
        return frozenset(p.code for r in self.roles for p in r.permissions)

    @property
    def role_names(self) -> tuple[str, ...]:
        """Names of the granted roles. Used to offer switching choices (not for authorization)."""
        return tuple(sorted(r.name for r in self.roles))

    def permission_codes_of(self, role_name: str | None) -> frozenset[str]:
        """Permissions of a single active role (ADR-0078 §1).

        If ``role_name`` is ``None``, "all roles" = the union of held permissions.
        A role name that is not granted yields the empty set (so that if the role is removed
        after switching to it, no permissions remain).

        Permissions that do not apply to the seat (inside or outside the tenants) are dropped
        (ADR-0079 §1; no combining).
        """
        if role_name is None:
            granted = self.permission_codes
        else:
            granted = frozenset(p.code for r in self.roles if r.name == role_name for p in r.permissions)
        return within_the_seat(self.tenant_id is not None, granted)


class UserSessionBoundary(Base):
    """Sign-in boundary (ADR-0076 §8). One row per user.

    **Tokens issued before it cannot refresh or be reissued.** The server keeps no session
    record, so this is the only way to end earlier sign-ins when the password changes.

    ⚠ **Do not make it a ``users`` column.** An old migration (the setup ``0002``) writes
    ``users`` through this model, so adding a column breaks at a step before the migration
    that adds it.
    """

    __tablename__ = "user_session_boundaries"
    __table_args__ = declared(Tenancy.PERSONAL)

    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    valid_from = mapped_column(sa.DateTime(), nullable=False)

    user: Mapped[User] = relationship(back_populates="session_boundary")


class RefreshSession(Base):
    """Record per sign-in (ADR-0091). One row per sign-in; without a row, that sign-in has ended."""

    __tablename__ = "refresh_sessions"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The one that can receive a new token pair
    current_jti: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    #: The one accepted only right after rotation (the loser of concurrent refreshes)
    previous_jti: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    rotated_at = mapped_column(sa.DateTime(), nullable=True)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    #: ``reset`` (requested by the user) or ``invitation`` (invited by an administrator, who
    #: lets them choose the first password; ADR-0079 §5)
    purpose: Mapped[str] = mapped_column(
        sa.Enum("reset", "invitation", name="password_token_purpose", native_enum=False),
        nullable=False,
        default="reset",
        server_default="reset",
    )
    expires_at = mapped_column(sa.DateTime(), nullable=False)
    used_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


__all__ = ["PasswordResetToken", "RefreshSession", "User", "UserSessionBoundary", "user_roles"]
