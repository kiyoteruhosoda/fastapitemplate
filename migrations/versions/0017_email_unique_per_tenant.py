"""email unique per tenant

Narrow the uniqueness of ``users.email`` from the whole app to within a tenant (ADR-0079 §4).

The same person (same email) can exist in different assay tenants, and if they use two tenants of
this app, there are two users too. With app-wide uniqueness, they could not be created on first
sign-in to the second tenant. Uniqueness "within the same tenant" and "among people outside the
tenants" is checked by the app (``shared/infrastructure/sign_in_directory.py``).

The DB unique constraint is dropped, keeping only the lookup index. The original unique constraint
was created without a name, so the name is taken from the actual schema (MariaDB ``email``,
SQLite unnamed).

Revision ID: email_unique_per_tenant
Revises: split_system_authority
Create Date: 2026-10-22

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "email_unique_per_tenant"
down_revision = "split_system_authority"
branch_labels = None
depends_on = None

_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    found = [
        uc["name"]
        for uc in sa.inspect(op.get_bind()).get_unique_constraints("users")
        if uc["column_names"] == ["email"]
    ]
    with op.batch_alter_table("users", naming_convention=_CONVENTION) as batch:
        batch.drop_constraint(found[0] if found and found[0] else "uq_users_email", type_="unique")
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.create_unique_constraint("uq_users_email", ["email"])
