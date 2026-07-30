"""認可マスタデータの正本（ユビキタス言語: ロール / 権限 / 権限付与）。

ロール・権限コード・ロールへの権限付与・初期管理者は、アプリケーションが
起動時から正しく動作するために必須の「マスタデータ」である。値の重複定義に
よるドリフトを防ぐため、ここを唯一の出所（single source of truth）とし、

- マイグレーション（``migrations/versions/*_seed_master_data.py``）
- 投入スクリプト（``scripts/seed_master_data.py``）

の双方がこのモジュールを参照する。フレームワーク・DB に依存しない純データの
ため、どこからでも安全に import できる。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# --- ロール ------------------------------------------------------------------
# id は外部参照（user_roles 等）の安定キーとして固定する。
ROLES: Sequence[tuple[int, str]] = (
    (1, "admin"),
    (2, "manager"),
    (3, "member"),
    (4, "guest"),
)

# --- 権限コード（scope） -----------------------------------------------------
# 認可は scope（権限コード値）で行う。コードを安定キーとし、id は DB 採番に任せる。
PERMISSION_CODES: Sequence[str] = (
    "admin:system-settings",
    "user:manage",
    "role:manage",
    "permission:manage",
    "system:manage",
    "log:view",
    "dashboard:view",
    "gui:view",
    "item:view",
    "item:manage",
)

# --- ロールへの権限付与 ------------------------------------------------------
# ロール名 -> 付与する権限コードの集合。有効 scope は所属ロールの和集合。
ROLE_PERMISSIONS: Mapping[str, Sequence[str]] = {
    "admin": tuple(PERMISSION_CODES),  # 全権限
    "manager": (
        "item:view",
        "item:manage",
        "log:view",
        "dashboard:view",
        "gui:view",
    ),
    "member": (
        "item:view",
        "dashboard:view",
        "gui:view",
    ),
    "guest": (
        "dashboard:view",
        "gui:view",
    ),
}

# --- 初期管理者 --------------------------------------------------------------
# パスワードは環境変数 ``ADMIN_INITIAL_PASSWORD`` で上書きできる（推奨）。
# 未指定時はフォールバックハッシュ（平文 = ``DEFAULT_ADMIN_PASSWORD``）が使われる
# ため、本番では初回ログイン後に必ず変更すること。
#
# Domain 層は werkzeug に依存できない（``tests/unit/test_layer_dependencies.py``）
# ため、ハッシュは事前計算値を置く。平文との対応は
# ``tests/unit/test_master_data.py`` が検証する。
DEFAULT_ADMIN_ID: int = 1
DEFAULT_ADMIN_EMAIL: str = "admin@example.com"
DEFAULT_ADMIN_USERNAME: str = "admin"
DEFAULT_ADMIN_ROLE: str = "admin"
DEFAULT_ADMIN_PASSWORD: str = "admin@example.com"
DEFAULT_ADMIN_PASSWORD_HASH: str = (
    "scrypt:32768:8:1$KdSu5I3W0KXRnlgp$"
    "ba3c41ed36121ffc856549df8ad55f1924ba78721ba417d1c8ab3eb6fc16d93cb28c4412"
    "692d00a5e7e32f9325936c35fbb5b8ed0dd2cb3a06230989706df370"
)

__all__ = [
    "DEFAULT_ADMIN_EMAIL",
    "DEFAULT_ADMIN_ID",
    "DEFAULT_ADMIN_PASSWORD",
    "DEFAULT_ADMIN_PASSWORD_HASH",
    "DEFAULT_ADMIN_ROLE",
    "DEFAULT_ADMIN_USERNAME",
    "PERMISSION_CODES",
    "ROLES",
    "ROLE_PERMISSIONS",
]
