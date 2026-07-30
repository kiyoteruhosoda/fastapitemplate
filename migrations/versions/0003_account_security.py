"""account security (TOTP / passkey)

二要素認証（TOTP 共有鍵）とパスキー（WebAuthn 資格情報・チャレンジ）の
テーブルを追加する。定義の正本は
``bounded_contexts/account_security/infrastructure/account_security_models.py``。

Revision ID: account_security
Revises: seed_master_data
Create Date: 2026-07-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "account_security"
down_revision = "seed_master_data"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
# DB ネイティブ ENUM は使わない（CHECK 制約付き VARCHAR になる）
_CHALLENGE_PURPOSE = sa.Enum(
    "registration",
    "authentication",
    name="webauthn_challenge_purpose",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "totp_secrets",
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "passkey_credentials",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("credential_id", sa.String(length=255), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", _BIGINT, nullable=False),
        sa.Column("transports", sa.JSON(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("attestation_format", sa.String(length=64), nullable=True),
        sa.Column("aaguid", sa.String(length=64), nullable=True),
        sa.Column("backup_eligible", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("backup_state", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index("ix_passkey_credentials_user_id", "passkey_credentials", ["user_id"])
    op.create_table(
        "webauthn_challenges",
        sa.Column("challenge_id", sa.String(length=32), nullable=False),
        sa.Column("challenge", sa.String(length=255), nullable=False),
        sa.Column("purpose", _CHALLENGE_PURPOSE, nullable=False),
        sa.Column("user_id", _BIGINT, nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("challenge_id"),
    )
    op.create_index("ix_webauthn_challenges_expires_at", "webauthn_challenges", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_webauthn_challenges_expires_at", table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")
    op.drop_index("ix_passkey_credentials_user_id", table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
    op.drop_table("totp_secrets")
