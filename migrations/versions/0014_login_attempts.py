"""login attempts

Record of failures per account name (ADR-0076 §9). Kept in the DB rather than process memory
because Gunicorn runs several workers (otherwise one could try once per worker).

The primary key is (purpose, account name). The account name is **the email address as sent**,
not tied to an existing account (counting only existing ones would reveal existence by whether
a request is refused). Expired rows are cleaned up on every write.

**Only adds a table**; existing tables are untouched.

Revision ID: login_attempts
Revises: user_session_boundaries
Create Date: 2026-10-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "login_attempts"
down_revision = "user_session_boundaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("purpose IN ('login', 'password_reset')", name="ck_login_attempts_purpose"),
        sa.PrimaryKeyConstraint("purpose", "identifier"),
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
