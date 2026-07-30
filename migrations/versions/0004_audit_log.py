"""audit log

監査ログ（``audit_log``）テーブルを追加し、アプリログ（``log``）へ絞り込み用の
索引を足す。定義の正本は
``bounded_contexts/audit/infrastructure/audit_log_model.py`` と
``shared/infrastructure/models/log.py``。

``audit_log`` は追記専用の記録なので外部キーを張らない（ユーザーを削除しても
「誰が何をしたか」の行を残すため。ADR-0008）。

Revision ID: audit_log
Revises: account_security
Create Date: 2026-07-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "audit_log"
down_revision = "account_security"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
# DB ネイティブ ENUM は使わない（CHECK 制約付き VARCHAR になる）
_AUDIT_RESULT = sa.Enum("success", "failure", name="audit_result", native_enum=False)

# log テーブルへ後から足す索引（管理画面の絞り込み軸）
_LOG_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_log_level", "level"),
    ("ix_log_logger", "logger"),
    ("ix_log_user_id_hash", "user_id_hash"),
)


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("result", _AUDIT_RESULT, nullable=False),
        sa.Column("actor_user_id", _BIGINT, nullable=True),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_result", "audit_log", ["result"])
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_log_target_type", "audit_log", ["target_type"])
    op.create_index("ix_audit_log_request_id", "audit_log", ["request_id"])

    for index_name, column in _LOG_INDEXES:
        op.create_index(index_name, "log", [column])


def downgrade() -> None:
    for index_name, _ in reversed(_LOG_INDEXES):
        op.drop_index(index_name, table_name="log")

    op.drop_index("ix_audit_log_request_id", table_name="audit_log")
    op.drop_index("ix_audit_log_target_type", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_user_id", table_name="audit_log")
    op.drop_index("ix_audit_log_result", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_table("audit_log")
