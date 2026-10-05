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
#
# ロールは「何を扱うか」の系統で分ける（ADR-0051）。
#
# - 全体:       owner（全権限。持ち主・最後の砦。ADR-0052）
# - システム:   system-admin（設定・再起動・アプリログ）
# - 人:         user-admin（利用者・グループの管理と、自分の範囲内のロールの付け外し）
# - 監査:       auditor（監査ログ・アプリログを読むだけ）
# - コンテンツ: manager（中身の管理）/ member（読む）/ guest（入れるだけ）
#
# 派生アプリでは、コンテンツの系統を自分の資源に合わせて組み替える
# （例: editor / publisher / moderator）。系統をまたぐロールは作らない。
ROLES: Sequence[tuple[int, str]] = (
    (1, "owner"),
    (2, "manager"),
    (3, "member"),
    (4, "guest"),
    (5, "system-admin"),
    (6, "user-admin"),
    (7, "auditor"),
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
    # 監査ログ（誰が何をしたか）の閲覧。アプリログ（log:view）とは別の scope に
    # している。「誰が」を追える記録は運用ログより取り扱いが重いため（ADR-0013）。
    "audit:view",
    "dashboard:view",
    "gui:view",
    "item:view",
    "item:manage",
    # グループ（利用者のまとまり）の作成・編集・所属の変更（ADR-0047）。
    "group:manage",
    # 管理画面からのお知らせの配信。宛先を選ぶためにグループと利用者の一覧も読める
    # （ADR-0047）。
    "notification:send",
)

# --- ロールへの権限付与 ------------------------------------------------------
# ロール名 -> 付与する権限コードの集合。有効 scope は所属ロールの和集合。
ROLE_PERMISSIONS: Mapping[str, Sequence[str]] = {
    "owner": tuple(PERMISSION_CODES),  # 全権限
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
    # システムの系統。中身（item:*）にも人（user:* / role:*）にも触れない。
    "system-admin": (
        "admin:system-settings",
        "system:manage",
        "log:view",
        "dashboard:view",
        "gui:view",
    ),
    # 人の系統。配れるのは自分が持つ権限の範囲のロールだけなので（ADR-0051）、
    # member と同じ閲覧の権限を持たせ、member・guest を割り当てられるようにしてある。
    # manager・admin への引き上げは、それを持つ人の仕事。
    "user-admin": (
        "user:manage",
        "group:manage",
        "item:view",
        "dashboard:view",
        "gui:view",
    ),
    # 監査の系統。読むだけ。変える権限は 1 つも持たせない（職務の分離）。
    "auditor": (
        "audit:view",
        "log:view",
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
DEFAULT_ADMIN_ROLE: str = "owner"
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
