"""password is optional (make users without local authentication representable in data)

Make ``users.password_hash`` nullable and **turn the random values stored for users created via
SSO into NULL** (ADR-0076 §6).

⚠ **Relaxing the column alone does not fix it.** Keeping the random values leaves "no password"
and "a password nobody knows" indistinguishable, and users who go through a password reset gain
local authentication.

⚠ **Which rows hold random values cannot be told from the values.** The only clue is **whether
the user row and the IdP link were created at the same time**: only when created via SSO
(``provision``) are the two born in the same transaction. For users linked to an existing
account later, the link is created days afterwards. The boundary here is **60 seconds**.

⚠ **A mistake can only lock people out, never let more in.** If too many are dropped, those users
have an administrator set a password (a noticeable failure). If too many are kept, an entrance is
silently added (unnoticeable). Being asymmetric, it errs on the side of dropping.

Revision ID: password_is_optional
Revises: backchannel_logout
Create Date: 2026-09-14

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "password_is_optional"
down_revision = "backchannel_logout"
branch_labels = None
depends_on = None

#: Window (seconds) within which a user row and its link count as "created at the same time".
_PROVISIONED_WITHIN_SECONDS = 60

#: The expression for the difference in seconds differs per dialect (SQLite has no ``TIMESTAMPDIFF``).
_ELAPSED_SECONDS = {
    "sqlite": "(julianday(f.created_at) - julianday(u.created_at)) * 86400",
    "postgresql": "EXTRACT(EPOCH FROM (f.created_at - u.created_at))",
    "mysql": "TIMESTAMPDIFF(SECOND, u.created_at, f.created_at)",
    "mariadb": "TIMESTAMPDIFF(SECOND, u.created_at, f.created_at)",
}


def upgrade() -> None:
    # ⚠ **A plain ``alter_column`` produces SQL that SQLite cannot run**:
    #   it emits ``ALTER TABLE users ALTER COLUMN ... DROP NOT NULL`` (on MariaDB it turns into
    #   ``MODIFY``, so watching production alone hides it). Whether it passes depends on the
    #   alembic version, so pin it to the form that rebuilds the table.
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)
    elapsed = _ELAPSED_SECONDS.get(op.get_bind().dialect.name)
    if elapsed is None:
        # Do not touch unknown dialects. **Doing nothing is better than silently dropping
        # everyone's password** (remedy in docs/OPERATIONS.md).
        return
    op.execute(
        sa.text(
            "UPDATE users SET password_hash = NULL WHERE id IN ("
            " SELECT user_id FROM ("
            "  SELECT f.user_id AS user_id FROM federated_identities f"
            "  JOIN users u ON u.id = f.user_id"
            f"  WHERE {elapsed} BETWEEN 0 AND {_PROVISIONED_WITHIN_SECONDS}"
            " ) AS provisioned"
            ")"
        )
    )


def downgrade() -> None:
    # ⚠ **Dropped values cannot be restored.** Going back to NOT NULL with NULLs fails, so rows
    #   that cannot be refilled get **a value nobody knows** (matching the original shape).
    op.execute(sa.text("UPDATE users SET password_hash = 'pbkdf2:sha256:unusable' WHERE password_hash IS NULL"))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
