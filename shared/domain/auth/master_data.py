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
# ロールは「何を扱うか」の系統で分ける（ADR-0078 §4）。
#
# 1 つのロールは 1 つのアクター（システムを使う人）に当たる（ADR-0084）。
#
# テナントの外側（ADR-0079 §1）。テナントに属さない利用者だけが持つ。
# - 運用者:         system-admin（テナントの登録・停止・削除、全体の設定・再起動・アプリログ）
# - サポート担当:   system-support（テナントの一覧と状態、システムの状態を見るだけ）
#
# テナントの内側。効くのは自分のテナントの中だけ。
# - テナント管理者:   owner（内側の全権限。ADR-0078 §5）
# - 利用者管理者:     user-admin（利用者・グループの管理と、自分の範囲内のロールの付け外し）
# - コンテンツ管理者: content-admin（コンテンツ設定を決める。中身は読むだけ）
# - 編集者:           manager（中身を作る・直す・消す）
# - 閲覧者:           member（読む）/ guest（入れるだけ）
# - 監査者:           auditor（監査ログとコンテンツ設定を見るだけ）
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
    (8, "system-support"),
    (9, "content-admin"),
)

# --- 権限コード（scope） -----------------------------------------------------
# 認可は scope（権限コード値）で行う。コードを安定キーとし、id は DB 採番に任せる。
PERMISSION_CODES: Sequence[str] = (
    # --- テナントの外側（SYSTEM_PERMISSIONS） ---
    # システム設定（/api/admin/config）。見ると変えるを分ける（ADR-0084 §3）。
    "system-settings:view",
    "system-settings:write",
    # システムの状態を見る（/api/admin/system/status）。
    "system:view",
    # 再起動と、テナントの外の人（運用者・サポート担当）の付け外し。
    "system:manage",
    "log:view",
    # テナントの一覧と状態を見る。
    "tenant:view",
    # テナントの登録・停止・削除と、最初のテナント管理者の指名（ADR-0079 §1）。
    "tenant:manage",
    # --- テナントの内側 ---
    # コンテンツ設定（そのテナントの中身の決まり。ADR-0084 §3）。
    "content-settings:view",
    "content-settings:write",
    "user:manage",
    # ロールの定義。権限コードの一覧も、ロールを定義するためにこれで読む（ADR-0084 §3）。
    "role:manage",
    # 監査ログ（誰が何をしたか）の閲覧。アプリログ（log:view）とは別の scope に
    # している。「誰が」を追える記録は運用ログより取り扱いが重いため（ADR-0075 §1）。
    "audit:view",
    "dashboard:view",
    "gui:view",
    "item:view",
    "item:write",
    # 共有メモ（bounded_contexts/notes。ADR-0078 §6 の見本）。scope が決めるのは「機能を使えるか」
    # まで。どのメモを読めて変えられるかは、持ち主とグループの所属で DB が決める。
    "note:view",
    "note:write",
    # グループ（利用者のまとまり）の作成・編集・所属の変更（ADR-0081 §3）。
    "group:manage",
    # 管理画面からのお知らせの配信。宛先を選ぶためにグループと利用者の一覧も読める
    # （ADR-0081 §3）。
    "notification:send",
)

# --- テナントの外側（ADR-0079 §1） ------------------------------------------------
# アプリ全体に効く権限。テナントの中のロールには持たせない ——持たせると、ある
# テナントの管理者がほかのテナントの設定や再起動まで動かせる。
SYSTEM_PERMISSIONS: Sequence[str] = (
    "system-settings:view",
    "system-settings:write",
    "system:view",
    "system:manage",
    "log:view",
    "tenant:view",
    "tenant:manage",
)

# テナントに属さない利用者だけが持つロール。テナントの利用者には付けられず、
# テナントに属さない利用者にはこれ以外を付けられない（兼ねない）。
SYSTEM_ROLES: Sequence[str] = ("system-admin", "system-support")

# 運用者（システム管理者）のロール。テナントを管理できる人を 0 人にしない数え方と、
# 据え付けの道具（scripts/create_system_admin.py）が使う。
SYSTEM_ADMIN_ROLE: str = "system-admin"

_TENANT_PERMISSIONS = tuple(code for code in PERMISSION_CODES if code not in SYSTEM_PERMISSIONS)

# --- ロールへの権限付与 ------------------------------------------------------
# ロール名 -> 付与する権限コードの集合。有効 scope は所属ロールの和集合。
ROLE_PERMISSIONS: Mapping[str, Sequence[str]] = {
    "owner": _TENANT_PERMISSIONS,  # テナントの内側の全権限（テナント管理者）
    # 編集者。中身を作る・直す・消す。
    "manager": (
        "item:view",
        "item:write",
        "note:view",
        "note:write",
        "dashboard:view",
        "gui:view",
    ),
    "member": (
        "item:view",
        "note:view",
        "dashboard:view",
        "gui:view",
    ),
    "guest": (
        "dashboard:view",
        "gui:view",
    ),
    # 運用者（テナントの外側）。中身（item:*）にも、テナントの人（user:* / role:*）にも
    # 触れない。監査ログは全体の操作の記録だけが見える（テナントの記録は見えない）。
    "system-admin": (
        *SYSTEM_PERMISSIONS,
        "audit:view",
        "dashboard:view",
        "gui:view",
    ),
    # サポート担当（テナントの外側）。問い合わせに答えるために状態を見るだけ。
    # 設定・アプリログ・監査ログは持たせない（利用者の情報が混じる。ADR-0084 §2）。
    "system-support": (
        "system:view",
        "tenant:view",
        "dashboard:view",
        "gui:view",
    ),
    # 人の系統。配れるのは自分が持つ権限の範囲のロールだけなので（ADR-0078 §4）、
    # member と同じ閲覧の権限を持たせ、member・guest を割り当てられるようにしてある。
    # manager・owner への引き上げは、それを持つ人の仕事。
    "user-admin": (
        "user:manage",
        "group:manage",
        "item:view",
        "note:view",
        "dashboard:view",
        "gui:view",
    ),
    # コンテンツ管理者。コンテンツの決まりを変え、中身は読むだけ。中身も直す人には
    # manager も付ける（系統をまたぐロールは作らない。ADR-0078 §4）。
    "content-admin": (
        "content-settings:view",
        "content-settings:write",
        "item:view",
        "note:view",
        "dashboard:view",
        "gui:view",
    ),
    # 監査の系統。読むだけ。変える権限は 1 つも持たせない（職務の分離）。
    # アプリログ（log:view）はアプリ全体のものなので持たせない（ADR-0079 §1）。
    # 中身も読ませない（確かめるのは記録と決まり。ADR-0084 §2）。
    "auditor": (
        "audit:view",
        "content-settings:view",
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
    "SYSTEM_ADMIN_ROLE",
    "SYSTEM_PERMISSIONS",
    "SYSTEM_ROLES",
]
