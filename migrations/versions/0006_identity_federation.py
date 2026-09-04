"""identity federation (SSO)

外部 IdP との SSO（ADR-0025）で要るテーブルを追加する。定義の正本は
``bounded_contexts/identity_federation/infrastructure/identity_federation_models.py``。

**表は 2 つだけ。** 認可要求の往復状態（``state`` / ``nonce`` / ``code_verifier``）は
署名付き Cookie でブラウザに預けるので、控えの表を持たない（ADR-0025）。保管も
掃除も要らず、``state`` を知っているだけの相手は戻りを完了できない。

Revision ID: identity_federation
Revises: seed_audit_permission
Create Date: 2026-09-04

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "identity_federation"
down_revision = "seed_audit_permission"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    # IdP のアカウントと利用者の結び付き。鍵は (issuer, subject)。
    # 利用者側に一意制約は置かない（1 人が複数の IdP アカウントを持てる）。
    op.create_table(
        "federated_identities",
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("issuer", "subject"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_federated_identities_user_id", "federated_identities", ["user_id"])

    # コールバックが発行する 1 回限りの引き換え券。**ハッシュだけを保存する**
    # （漏れた控えからそのままログインできないようにする）。
    op.create_table(
        "sso_login_tickets",
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("redirect_to", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("ticket_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sso_login_tickets_user_id", "sso_login_tickets", ["user_id"])
    # 期限切れは券を発行するたびに掃除するので、定期ジョブは持たない。
    op.create_index("ix_sso_login_tickets_expires_at", "sso_login_tickets", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sso_login_tickets_expires_at", table_name="sso_login_tickets")
    op.drop_index("ix_sso_login_tickets_user_id", table_name="sso_login_tickets")
    op.drop_table("sso_login_tickets")
    op.drop_index("ix_federated_identities_user_id", table_name="federated_identities")
    op.drop_table("federated_identities")
