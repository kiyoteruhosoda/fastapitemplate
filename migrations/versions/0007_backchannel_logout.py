"""back-channel logout (停止の伝播の受け口)

IdP から届いた「このセッションを止めろ」を記録する表を追加し、引き換え券に
**どの IdP セッションから始まったログインか**を持たせる（ADR-0036）。

⚠ **引き換え券は作り直す。** 追加する 3 列は NOT NULL だが、券の寿命は 60 秒なので
残しても意味が無い。既存の行は消してから列を足す（使い切る前の券があった場合は
ログインをやり直してもらう）。

Revision ID: backchannel_logout
Revises: identity_federation
Create Date: 2026-09-14

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "backchannel_logout"
down_revision = "identity_federation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 停止の記録。主キーが jti なのは、**再送を行の重複としてそのまま弾く**ため
    # （送り手は再送でも同じ jti を使う。idp の ADR-0024）。
    op.create_table(
        "federated_session_revocations",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        # NULL = その利用者のすべてのセッション（通知に sid が無かった場合）
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index(
        "ix_federated_session_revocations_subject",
        "federated_session_revocations",
        ["issuer", "subject"],
    )
    # 期限切れは通知を受けるたびに掃除するので、定期ジョブは持たない。
    op.create_index(
        "ix_federated_session_revocations_expires_at",
        "federated_session_revocations",
        ["expires_at"],
    )

    op.execute(sa.text("DELETE FROM sso_login_tickets"))
    op.add_column("sso_login_tickets", sa.Column("issuer", sa.String(length=255), nullable=False))
    op.add_column("sso_login_tickets", sa.Column("subject", sa.String(length=255), nullable=False))
    op.add_column("sso_login_tickets", sa.Column("session_id", sa.String(length=255), nullable=True))
    op.add_column("sso_login_tickets", sa.Column("session_started_at", sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_column("sso_login_tickets", "session_started_at")
    op.drop_column("sso_login_tickets", "session_id")
    op.drop_column("sso_login_tickets", "subject")
    op.drop_column("sso_login_tickets", "issuer")
    # ⚠ **索引は単独で落とさない。** ``DROP TABLE`` が一緒に消すので不要で、外部キー列の
    #   索引だと MariaDB では 1553 で落ちる（SQLite は通るので手元では気付けない）。
    op.drop_table("federated_session_revocations")
