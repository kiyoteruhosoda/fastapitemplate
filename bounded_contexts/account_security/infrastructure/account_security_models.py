"""SQLAlchemy models of the account security context.

``migrations/env.py`` and ``tests/conftest.py`` import this module to register it in the
metadata (handling of context-specific models; see "DDL management" in CLAUDE.md).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bounded_contexts.account_security.domain.entities.login_attempts import ATTEMPT_PURPOSES
from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    CHALLENGE_PURPOSES,
)
from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class TotpSecretRecord(Base):
    """TOTP shared key (one row per user)."""

    __tablename__ = "totp_secrets"
    __table_args__ = declared(Tenancy.PERSONAL)

    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    # While NULL, enrollment is in progress. Two-factor authentication is not enabled yet.
    confirmed_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class PasskeyCredentialRecord(Base):
    """WebAuthn credential (passkey)."""

    __tablename__ = "passkey_credentials"
    __table_args__ = declared(Tenancy.PERSONAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # base64url string. The owner is looked up by this value at authentication.
    credential_id: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    public_key: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    sign_count: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        nullable=False,
        default=0,
    )
    transports = mapped_column(sa.JSON(), nullable=True)
    name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    attestation_format: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    aaguid: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    backup_eligible: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False, server_default=sa.false()
    )
    backup_state: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False, server_default=sa.false())
    last_used_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class WebAuthnChallengeRecord(Base):
    """Issued challenges.

    Gunicorn runs multiple workers, so the issuing process and the verifying process
    may differ. Kept in the DB rather than process memory.
    """

    __tablename__ = "webauthn_challenges"
    __table_args__ = declared(Tenancy.PERSONAL)

    challenge_id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    challenge: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # No DB-native ENUM; use VARCHAR with a CHECK (CLAUDE.md)
    purpose: Mapped[str] = mapped_column(
        sa.Enum(*CHALLENGE_PURPOSES, name="webauthn_challenge_purpose", native_enum=False),
        nullable=False,
    )
    # Nullable because the user is unknown when a login challenge is issued
    user_id: Mapped[int | None] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


class LoginAttemptRecord(Base):
    """Failure records per submitted identifier (ADR-0076 §9).

    The identifier is **the email address that was submitted** and is not linked to ``users``.
    Counting only existing accounts would reveal whether an account exists by whether it gets
    refused. Expired rows are cleaned up on every write.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        sa.CheckConstraint(f"purpose IN {ATTEMPT_PURPOSES}", name="ck_login_attempts_purpose"),
        # The identifier is the submitted email address, linked to neither a user nor a tenant
        declared(Tenancy.GLOBAL),
    )

    purpose: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    identifier: Mapped[str] = mapped_column(sa.String(255), primary_key=True)
    failures: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0, server_default="0")
    window_started_at = mapped_column(sa.DateTime(), nullable=True)
    locked_until = mapped_column(sa.DateTime(), nullable=True)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = [
    "LoginAttemptRecord",
    "PasskeyCredentialRecord",
    "TotpSecretRecord",
    "WebAuthnChallengeRecord",
]
