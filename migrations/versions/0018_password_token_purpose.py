"""password token purpose

``password_reset_tokens.purpose`` を足す（ADR-0065）。``reset`` は本人の申し込み、``invitation`` は
管理者の招待で、招待だけはパスワードを持たない利用者に最初のパスワードを決めさせる
（ADR-0038 の「持たせるのは管理者が明示的に設定したとき」に当たる）。

いまある行は全部 ``reset``。

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
