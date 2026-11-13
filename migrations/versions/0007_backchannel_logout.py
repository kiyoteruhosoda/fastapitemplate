"""back-channel logout (receiving end for propagated revocation)

Add a table recording "stop this session" notices from the IdP, and make the exchange ticket carry
**which IdP session the sign-in started from** (ADR-0077 §3).

⚠ **Exchange tickets are recreated.** The 3 added columns are NOT NULL, but tickets live only 60
seconds, so keeping them is pointless. Existing rows are deleted before adding the columns (anyone
with an unused ticket simply signs in again).

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
    # Revocation records. The primary key is the jti so that **resends are rejected as duplicate
    # rows** (the sender reuses the same jti when resending; idp ADR-0024).
    op.create_table(
        "federated_session_revocations",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        # NULL = all sessions of the user (when the notice had no sid)
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
    # Expired rows are cleaned up on every notice, so there is no periodic job.
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
    # ⚠ **Do not drop the index on its own.** ``DROP TABLE`` removes it anyway, and for an index on a
    #   foreign key column MariaDB fails with 1553 (SQLite passes, so it goes unnoticed locally).
    op.drop_table("federated_session_revocations")
