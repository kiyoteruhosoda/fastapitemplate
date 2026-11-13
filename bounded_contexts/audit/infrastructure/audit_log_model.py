"""SQLAlchemy model of the ``audit_log`` table (specific to the audit context).

It is an append-only record, so it has no foreign keys: rows of "who did what" must remain even
when the user is deleted (ADR-0075 §1).

Imported in ``migrations/env.py`` and ``tests/conftest.py`` so Alembic and the tests see it.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bounded_contexts.audit.domain.entities.audit_event import AuditResult
from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base

# No DB-native ENUM (becomes a VARCHAR with a CHECK constraint; "DB modeling" in CLAUDE.md).
# Allowed values are managed centrally on the Python side in AuditResult.
_AUDIT_RESULT = sa.Enum(
    *(result.value for result in AuditResult),
    name="audit_result",
    native_enum=False,
)


class AuditLogModel(Base):
    __tablename__ = "audit_log"
    __table_args__ = declared(Tenancy.TENANT)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    # Which tenant the record belongs to. NULL is a global operation (system administrators,
    # failures with unknown target).
    # ⚠ No foreign key (records stay when a tenant is deleted; same reason as ADR-0075 §1)
    tenant_id = mapped_column(BigIntPk, nullable=True, index=True)
    occurred_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    result: Mapped[str] = mapped_column(_AUDIT_RESULT, nullable=False, index=True)
    # Internal ID of the user who performed the operation. NULL for failures before authentication
    # (sign-in with an unregistered email).
    actor_user_id = mapped_column(BigIntPk, nullable=True, index=True)
    target_type = mapped_column(sa.String(64), nullable=True, index=True)
    target_id = mapped_column(sa.String(64), nullable=True)
    ip_address = mapped_column(sa.String(45), nullable=True)
    user_agent = mapped_column(sa.String(512), nullable=True)
    # Failure reason or changed item names. Never the values themselves (PII).
    reason = mapped_column(sa.String(255), nullable=True)
    # Same value as log.request_id. Tracking key to match application logs and audit logs.
    request_id = mapped_column(sa.String(36), nullable=True, index=True)


__all__ = ["AuditLogModel"]
