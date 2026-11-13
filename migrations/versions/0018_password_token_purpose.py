"""password token purpose

Add ``password_reset_tokens.purpose`` (ADR-0079 §5). ``reset`` is requested by the user;
``invitation`` is an administrator's invitation, and only an invitation lets a user without a
password choose their first one (the "given only when an administrator explicitly sets it" case
of ADR-0076 §6).

All existing rows are ``reset``.

Revision ID: password_token_purpose
Revises: email_unique_per_tenant
Create Date: 2026-10-22

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "password_token_purpose"
down_revision = "email_unique_per_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("password_reset_tokens") as batch:
        batch.add_column(
            sa.Column(
                "purpose",
                sa.Enum("reset", "invitation", name="password_token_purpose", native_enum=False),
                nullable=False,
                server_default="reset",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("password_reset_tokens") as batch:
        batch.drop_column("purpose")
