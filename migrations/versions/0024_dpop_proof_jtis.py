"""dpop proof jtis

Add ``dpop_proof_jtis``, the record that accepts each received DPoP proof only once per key
(ADR-0103). The definition lives in
``bounded_contexts/identity_federation/infrastructure/identity_federation_models.py``.

Revision ID: dpop_proof_jtis
Revises: item_timestamps
Create Date: 2026-11-04

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "dpop_proof_jtis"
down_revision = "item_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dpop_proof_jtis",
        sa.Column("replay_key", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("replay_key"),
    )
    op.create_index("ix_dpop_proof_jtis_expires_at", "dpop_proof_jtis", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_dpop_proof_jtis_expires_at", table_name="dpop_proof_jtis")
    op.drop_table("dpop_proof_jtis")
