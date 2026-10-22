"""email unique per tenant

``users.email`` の一意をアプリ全体からテナントの中へ狭める（ADR-0064）。

assay の別々のテナントに同じ人（同じメールアドレス）が居ることはあり、その人がこのアプリの
2 つのテナントを使えば、利用者も 2 人になる。全体で一意のままだと、2 つ目のテナントで
初めて入ったときに作れない。一意は「同じテナントの中」「テナントに属さない人の中」で
アプリが確かめる（``shared/infrastructure/sign_in_directory.py``）。

DB の一意制約は外し、引くための索引だけを残す。元の一意制約は名前を付けずに作っているので、
名前は実物から引く（MariaDB は ``email``、SQLite は無名）。

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
