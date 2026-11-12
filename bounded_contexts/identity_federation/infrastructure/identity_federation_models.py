"""SQLAlchemy models of the identity federation context.

``migrations/env.py`` and ``tests/conftest.py`` import this module to register it in the
metadata (handling of context-specific models. CLAUDE.md "DDL management").
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class FederatedIdentityRecord(Base):
    """Binding between an external IdP account and a user.

    Keyed by ``(issuer, subject)``. No uniqueness constraint on the user side (one person can
    have multiple IdP accounts).
    """

    __tablename__ = "federated_identities"
    __table_args__ = declared(Tenancy.PERSONAL)

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
    """Single-use redemption ticket issued by the callback (only the hash is stored).

    It also carries the IdP-side session (``issuer`` / ``subject`` / ``session_id``).
    Logout propagation arrives addressed by this triple, so **unless it is recorded when the
    ticket is issued, it can't be matched later** (ADR-0077 §3).
    """

    __tablename__ = "sso_login_tickets"
    __table_args__ = declared(Tenancy.PERSONAL)

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
    #: The ID token's ``sid``. Nullable because some IdPs don't provide it.
    session_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    #: When the session started. Logout records are compared against this time (ADR-0077 §3).
    session_started_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


class FederatedSessionRevocationRecord(Base):
    """Record of "stop this session" received from the IdP (ADR-0077 §3).

    The primary key is ``jti`` so that resends are **rejected as duplicate rows as is**
    (the sender in ADR-0078 §3 uses the same ``jti`` when resending).
    Rows with NULL ``session_id`` apply to all sessions of that user.
    """

    __tablename__ = "federated_session_revocations"
    __table_args__ = (
        sa.Index("ix_federated_session_revocations_subject", "issuer", "subject"),
        # Addressed by issuer and subject. The issuer represents the tenant, so there is no tenant column
        declared(Tenancy.GLOBAL),
    )

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


class DpopProofReplayRecord(Base):
    """Record making each received DPoP proof (``jti`` per key) single-use (ADR-0103).

    The primary key is hex of ``sha256(jkt ":" jti)``. Rows past the accepted window (up to 120 s before ``iat``)
    can be deleted, since the same proof is then refused by time. Expired rows are cleaned on each insert.
    """

    __tablename__ = "dpop_proof_jtis"
    # Only the key thumbprint and jti; whose it is isn't stored
    __table_args__ = declared(Tenancy.GLOBAL)

    replay_key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
