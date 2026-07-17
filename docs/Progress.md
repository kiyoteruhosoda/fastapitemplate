# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

- 状態: ⬜未着手 / 🚧進行中 / 🟡要判断
- 影響度・工数: 大 / 中 / 小

## テンプレート刷新（photonest 準拠）

photonest の構成・設計思想をベースに本テンプレートを刷新する。
**持ち込むもの**: DDD 4層構成・認証認可（scope ベース）・システム設定管理・
構造化ログ・UIスケルトン・Docker 構成・デプロイスクリプト・ドキュメント運用ルール。
**持ち込まないもの**: アルバム／メディア関連（albums, media, picker_import, storage,
photo_exports, tags）、バッチ（Celery worker / beat / Redis）、wiki、certs、
Google OAuth・Google Photos 連携。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T1 | ドキュメント・作業テンプレ基盤（CLAUDE.md、docs/ 一式） | 🚧進行中 | 大 | 小 |
| 2 | T2 | プロジェクト骨格の刷新（bounded_contexts / shared / presentation 構成へ） | ⬜未着手 | 大 | 中 |
| 3 | T3 | 設定管理（settings オブジェクト、優先順位: 環境変数 > DB > デフォルト） | ⬜未着手 | 大 | 中 |
| 4 | T4 | DB 基盤（SQLAlchemy 2.x + Alembic、ベースライン & シード） | ⬜未着手 | 大 | 中 |
| 5 | T5 | 認証・認可（JWT、ユーザー／ロール／権限 scope ベース） | ⬜未着手 | 大 | 大 |
| 6 | T6 | 管理 API（users / roles / permissions / config / logs） | ⬜未着手 | 中 | 中 |
| 7 | T7 | 構造化ログ（JSON 出力 + DB 書き込み、requestId 追跡） | ⬜未着手 | 中 | 中 |
| 8 | T8 | フロントエンドスケルトン（Vite + React + TS） | ⬜未着手 | 大 | 大 |
| 9 | T9 | Docker 構成（compose: db / web / nginx、マルチステージビルド） | ⬜未着手 | 大 | 中 |
| 10 | T10 | デプロイスクリプト（deploy.sh / entrypoint.sh / Makefile） | ⬜未着手 | 中 | 中 |
| 11 | T11 | テスト整備（unit / integration、モデル・マイグレーション整合性テスト） | ⬜未着手 | 中 | 中 |
| 12 | T12 | README・OPERATIONS 更新 | ⬜未着手 | 小 | 小 |
| — | T13 | DB エンジン選定（SQLite 継続 or MariaDB 併用） | 🟡要判断 | 大 | — |
| — | T14 | パスワードリセット（email_sender コンテキスト）を含めるか | 🟡要判断 | 中 | — |
| — | T15 | TOTP / パスキーを含めるか | 🟡要判断 | 中 | — |

---

## 詳細

- **T1 ドキュメント・作業テンプレ基盤** — photonest の CLAUDE.md をテンプレート向けに
  移植（ドキュメント運用ルール・設計方針・設定管理・API 設計・ログ・テスト規約）。
  `docs/ARCHITECTURE.md`、`docs/OPERATIONS.md`、`docs/CHANGELOG.md`、
  `docs/decisions/ADR-template.md`、`docs/history/` を作成。
  「開発開始時に Progress へ TODO 追加 → 完了時に CHANGELOG / history へ移す」という
  作業テンプレ指示自体をテンプレートの一部として残す。

- **T2 プロジェクト骨格の刷新** — 現行の `src/`（application / domain /
  infrastructure / presentation）を photonest 準拠の構成へ移行する:

  ```
  bounded_contexts/<context>/   # domain / application / infrastructure / presentation
  shared/
    kernel/                     # settings / logging / database / crypto / time / version
    domain/auth/                # ユーザー・ロール・権限・master_data
    infrastructure/             # 共有リポジトリ実装・モデル
  presentation/fastapi/         # app.py / routers / schemas / dependencies /
                                # middleware / services / admin
  ```

  既存の item サンプルは `bounded_contexts/example/` として再配置し、
  「新しいコンテキストの作り方」の見本として残す。

- **T3 設定管理** — `shared/kernel/settings/settings.py`（`@property` 経由の一元アクセス）、
  `system_settings_defaults.py`（デフォルト値）、
  `presentation/fastapi/admin/system_settings_definitions.py`（管理画面項目）の
  3ファイル構成を移植。直接 `os.getenv` / DB アクセスの禁止ルールも CLAUDE.md に明記。

- **T4 DB 基盤** — SQLAlchemy 2.x Declarative Base + Alembic。
  `migrations/versions/init_master.py`（ベースライン）と
  `*_seed_master_data.py`（ロール・権限・初期管理者。出所は
  `shared/domain/auth/master_data.py` に一元化）。
  BigInteger は `with_variant(sa.Integer(), "sqlite")` で SQLite テストと両立。
  DB ネイティブ ENUM 禁止（`native_enum=False`）。

- **T5 認証・認可** — JWT（access / refresh）によるログイン、パスワードハッシュ、
  ユーザー・ロール・権限モデル。認可はロール名ではなく **scope（権限コード値）** で行い、
  FastAPI の依存性（photonest の `dependencies/auth.py` 相当）でエンドポイントに
  権限コードを宣言する。JWT の scope は保有権限の範囲内。

- **T6 管理 API** — photonest の `routers/admin/` から users / roles / permissions /
  config（システム設定）/ logs を移植。albums・media・cdn・blob・photo_exports・
  service_accounts・impersonation は持ち込まない（service_accounts は将来必要に
  なったら photonest から移植する旨を ARCHITECTURE に注記）。

- **T7 構造化ログ** — JSON 形式で stdout 出力しつつ `log` テーブルへ書き込み。
  `requestId` でリクエスト単位に追跡。PII を含めない（`user.id_hash` のみ）。
  時刻は常に UTC。Celery を持ち込まないため `worker_log` / `taskId` は対象外。

- **T8 フロントエンドスケルトン** — photonest の `frontend/`（Vite + React + TS +
  i18n + store + services/api.ts）をベースに、以下のページのみ残したスケルトンにする:
  Login / ForgotPassword / ResetPassword / ChangePassword / Profile /
  AdminDashboard / Users / Roles / Permissions / Groups / Config（システム設定画面）/
  SystemLogs / Sessions。共通コンポーネント（Header / Sidebar / Footer /
  ToastNotification）も残す。アルバム・メディア・wiki 系ページは持ち込まない。
  SPA 配信は photonest の `routers/spa.py` 方式を踏襲。

- **T9 Docker 構成** — photonest の docker-compose をベースに
  `init-paths / db / web / nginx` の構成（worker / beat / redis は除外）。
  アプリ Dockerfile はフロントエンドビルドを含むマルチステージ、
  `db/Dockerfile`、`docker/nginx/default.conf` も移植。
  バージョン情報埋め込み（COMMIT_HASH 等の build-arg → version.json）を踏襲。

- **T10 デプロイスクリプト** — `scripts/deploy.sh`（stg / prod を配置ディレクトリで
  自動判定、app / migrate / reset モード）、`scripts/entrypoint.sh`（起動診断 +
  マイグレーション）、`scripts/generate_version.sh`、`scripts/seed_master_data.py`、
  Makefile（build / dist-assets / docker save tar）を photonest から移植し、
  プロジェクト名等をテンプレート用に汎用化。Celery・メディアディレクトリ関連の
  処理は削除。

- **T11 テスト整備** — `tests/unit/`（外部依存なし）と `tests/integration/`
  （DB 使用）。`--import-mode=importlib`。モデルとマイグレーションの乖離を検出する
  `test_migration_model_consistency.py` を移植。時刻・乱数・UUID はテスト内で固定。

- **T13 DB エンジン選定（要判断）** — photonest は MariaDB 10.11、現テンプレートは
  SQLite。**推奨: 本番 compose は MariaDB、ローカル開発・テストは SQLite** の
  二本立て（photonest の `with_variant` パターンで両立可能）。
  シンプルさ優先なら SQLite 単独も可。決定後 ADR-0001 として記録する。

- **T14 パスワードリセット（要判断）** — ForgotPassword / ResetPassword 画面を
  スケルトンとして残す場合、メール送信（email_sender コンテキスト + SMTP 設定）が
  必要になる。**推奨: email_sender を含めて移植**（テンプレートとして実用性が高い）。
  除外する場合は該当画面も落とす。

- **T15 TOTP / パスキー（要判断）** — photonest には TOTP・WebAuthn パスキーがあるが
  「基本的な認証」の範囲を超える。**推奨: 初期スコープからは除外**し、必要になったら
  photonest から移植する旨を ARCHITECTURE に注記。

### 実施順序

T1 → T2 → T3 → T4 → T5 →（T6 / T7 並行）→ T8 → T9 → T10 → T11 → T12。
T13〜T15 は T4 / T5 / T8 着手前に判断する。
