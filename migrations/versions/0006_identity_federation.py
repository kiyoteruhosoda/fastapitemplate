"""identity federation (SSO)

Add the tables needed for SSO with an external IdP (ADR-0077 §1). The definitions live in
``bounded_contexts/identity_federation/infrastructure/identity_federation_models.py``.

**Only two tables.** The round-trip state of the authorization request (``state`` / ``nonce`` /
``code_verifier``) is entrusted to the browser in a signed cookie, so there is no table for it
(ADR-0077 §1). Nothing to store or clean up, and someone who only knows ``state`` cannot
complete the callback.

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
    # Link between IdP accounts and users. The key is (issuer, subject).
    # No unique constraint on the user side (one person can have several IdP accounts).
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

    # One-time exchange ticket issued by the callback. **Only the hash is stored**
    # (so a leaked record cannot be used to sign in directly).
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
    # Expired tickets are cleaned up whenever a ticket is issued, so there is no periodic job.
    op.create_index("ix_sso_login_tickets_expires_at", "sso_login_tickets", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sso_login_tickets_expires_at", table_name="sso_login_tickets")
    op.drop_index("ix_sso_login_tickets_user_id", table_name="sso_login_tickets")
    op.drop_table("sso_login_tickets")
    op.drop_index("ix_federated_identities_user_id", table_name="federated_identities")
    op.drop_table("federated_identities")
