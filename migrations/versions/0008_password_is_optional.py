"""password is optional (ローカル認証を持たない利用者をデータで表せるようにする)

``users.password_hash`` を NULL 許容へ移し、**SSO で作られた利用者に入っていた
ランダム値を NULL へ落とす**（ADR-0038）。

⚠ **列を緩めるだけでは直らない。** ランダム値を残すと「パスワードが無い」と
「誰も知らないパスワードがある」が区別できないままで、パスワードリセットを通した
利用者にローカル認証が生える。

⚠ **どの行がランダム値かは、値からは分からない。** 手掛かりは
**利用者の行と IdP との結び付きが同時に作られたか**しかない ——SSO で作った
（``provision``）場合だけ、この 2 つが同じトランザクションで生まれる。既存の口座へ
後から寄せた利用者は、結び付きのほうが何日もあとに作られる。ここでは
**60 秒**を境にする。

⚠ **取り違えても入れなくなるだけで、増えることはない。** 落としすぎた場合、その
利用者は管理者にパスワードを設定してもらうことになる（気付ける失敗）。逆に残した
場合は黙って入り口が 1 つ増える（気付けない）。非対称なので、落とす側へ倒す。

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

#: 利用者の行と結び付きが「同時に作られた」と見なす幅（秒）。
_PROVISIONED_WITHIN_SECONDS = 60

#: 秒差を出す式は方言ごとに違う（``TIMESTAMPDIFF`` は SQLite に無い）。
_ELAPSED_SECONDS = {
    "sqlite": "(julianday(f.created_at) - julianday(u.created_at)) * 86400",
    "postgresql": "EXTRACT(EPOCH FROM (f.created_at - u.created_at))",
    "mysql": "TIMESTAMPDIFF(SECOND, u.created_at, f.created_at)",
    "mariadb": "TIMESTAMPDIFF(SECOND, u.created_at, f.created_at)",
}


def upgrade() -> None:
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    elapsed = _ELAPSED_SECONDS.get(op.get_bind().dialect.name)
    if elapsed is None:
        # 知らない方言では触らない。**黙って全員のパスワードを落とすより、
        # 何もしないほうがましである**（手当ては docs/OPERATIONS.md）。
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
    # ⚠ **落とした値は戻らない。** NULL のまま NOT NULL へ戻すと通らないので、
    #   入れ直せない行には**誰も知らない値**を入れる（元の形に合わせる）。
    op.execute(sa.text("UPDATE users SET password_hash = 'pbkdf2:sha256:unusable' WHERE password_hash IS NULL"))
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
