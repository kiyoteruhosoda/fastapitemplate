"""tenants

テナントを足す（ADR-0061）。

- ``tenants`` —— assay のテナント 1 つに 1 行（発行者・クライアント ID・短い名前・状態）
- ``user_tenants`` —— 利用者の所属（1 人 1 行）。⚠ ``users`` の列にしない（据え付けの
  ``0002`` が ``User`` のモデルで ``users`` を書くので、列を足すとそこで落ちる）
- 中身の表（``items`` / ``user_groups`` / ``notifications`` / ``audit_log``）に ``tenant_id``

**既存の環境は「既定のテナント」1 つに全員を入れて移る**（決定 9）。発行者とクライアント ID は
いまの ``OIDC_ISSUER`` / ``OIDC_CLIENT_ID``（画面で保存した値があればそちら）から取る。
グループの名前の一意はテナントの中へ狭める。

モデルは使わない（Core だけで書く）。この移行より後でモデルが変わっても、ここが落ちないように。

Revision ID: tenants
Revises: login_attempts
Create Date: 2026-10-22

"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "tenants"
down_revision = "login_attempts"
branch_labels = None
depends_on = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_STATUS = sa.Enum("active", "suspended", name="tenant_status", native_enum=False)
_DEFAULT_SLUG = "default"
_DEFAULT_NAME = "Default"

#: 中身の表。``tenant_id`` は NOT NULL で、既定のテナントを入れてから締める。
_CONTENT_TABLES = ("items", "user_groups", "notifications")


def _configured(key: str) -> str:
    """画面で保存した値（``system_settings`` の ``app.config``）、無ければ環境変数。"""
    from shared.kernel.settings.settings import settings

    row = (
        op.get_bind()
        .execute(sa.text("SELECT setting_json FROM system_settings WHERE setting_key = 'app.config'"))
        .first()
    )
    payload = row[0] if row is not None else None
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict) and payload.get(key):
        return str(payload[key])
    return settings.oidc_issuer if key == "OIDC_ISSUER" else settings.oidc_client_id


def _create_tables() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=True),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("status", _STATUS, server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("issuer"),
    )
    op.create_table(
        "user_tenants",
        sa.Column("user_id", _BIGINT, nullable=False),
        sa.Column("tenant_id", _BIGINT, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_user_tenants_tenant_id", "user_tenants", ["tenant_id"])


def _seat_everyone() -> int:
    """既定のテナントを作り、全利用者を入れる。作ったテナントの ID を返す。"""
    bind = op.get_bind()
    issuer = _configured("OIDC_ISSUER").rstrip("/")
    client_id = _configured("OIDC_CLIENT_ID")
    tenants = sa.table(
        "tenants",
        sa.column("slug", sa.String),
        sa.column("display_name", sa.String),
        sa.column("issuer", sa.String),
        sa.column("client_id", sa.String),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    from shared.kernel.timestamps import utcnow

    bind.execute(
        tenants.insert().values(
            slug=_DEFAULT_SLUG,
            display_name=_DEFAULT_NAME,
            issuer=issuer or None,
            client_id=client_id or None,
            status="active",
            created_at=utcnow(),
        )
    )
    tenant_id = int(bind.execute(sa.text("SELECT id FROM tenants WHERE slug = :s"), {"s": _DEFAULT_SLUG}).scalar_one())
    bind.execute(
        sa.text("INSERT INTO user_tenants (user_id, tenant_id) SELECT id, :t FROM users"),
        {"t": tenant_id},
    )
    return tenant_id


def _add_tenant_column(table: str, tenant_id: int) -> None:
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column("tenant_id", _BIGINT, nullable=True))
    op.get_bind().execute(sa.text(f"UPDATE {table} SET tenant_id = :t"), {"t": tenant_id})
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    with op.batch_alter_table(table) as batch:
        batch.alter_column("tenant_id", existing_type=_BIGINT, nullable=False)
        batch.create_foreign_key(f"fk_{table}_tenant_id", "tenants", ["tenant_id"], ["id"])


def _group_names_unique_per_tenant() -> None:
    """``user_groups.name`` の一意を ``(tenant_id, name)`` へ狭める。

    元の一意制約は名前を付けずに作っている。名前は DB が決める（MariaDB は ``name``、
    PostgreSQL は ``user_groups_name_key``）ので、実物から引く。SQLite は名前を持たないので、
    命名規則を当てて作り直す。
    """
    found = [
        uc["name"]
        for uc in sa.inspect(op.get_bind()).get_unique_constraints("user_groups")
        if uc["column_names"] == ["name"]
    ]
    old_name = found[0] if found else None
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("user_groups", naming_convention=convention) as batch:
        batch.drop_constraint(old_name or "uq_user_groups_name", type_="unique")
        batch.create_unique_constraint("uq_user_groups_tenant_name", ["tenant_id", "name"])


def upgrade() -> None:
    _create_tables()
    tenant_id = _seat_everyone()
    for table in _CONTENT_TABLES:
        _add_tenant_column(table, tenant_id)
    _group_names_unique_per_tenant()
    # 監査ログ。NULL は全体の操作。⚠ 外部キーを張らない（テナントを消しても記録は残す）。
    # いままでの記録は、いまの環境 ＝ 既定のテナントのもの。
    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("tenant_id", _BIGINT, nullable=True))
    op.get_bind().execute(sa.text("UPDATE audit_log SET tenant_id = :t"), {"t": tenant_id})
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_tenant_id", table_name="audit_log")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("tenant_id")
    with op.batch_alter_table("user_groups") as batch:
        batch.drop_constraint("uq_user_groups_tenant_name", type_="unique")
        batch.create_unique_constraint("uq_user_groups_name", ["name"])
    for table in reversed(_CONTENT_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_tenant_id", type_="foreignkey")
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("tenant_id")
    op.drop_index("ix_user_tenants_tenant_id", table_name="user_tenants")
    op.drop_table("user_tenants")
    op.drop_table("tenants")
