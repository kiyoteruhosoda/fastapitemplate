# 2026-07 テンプレート刷新（photonest 準拠）

photonest の構成・設計思想をベースに本テンプレートを全面刷新した。

## 持ち込んだもの

- DDD 4層 + `bounded_contexts/` 構成（`example/` = Item CRUD 見本、`email_sender/` = SMTP 送信）
- 認証・認可: JWT（access / refresh）+ scope（権限コード値）ベース。
  ロール・権限・初期管理者の正本は `shared/domain/auth/master_data.py`
- 設定管理: `settings` オブジェクト（環境変数 > DB > デフォルト、TTL キャッシュ付き
  DB 上書き層）+ 管理画面（Config）
- 構造化ログ: JSON stdout + `log` テーブル書き込み、`requestId` 追跡
- Alembic: `0001_init_master`（ベースライン）+ `0002_seed_master_data`
- フロントエンド: Vite + React + TS の SPA スケルトン
  （Login / パスワードリセット / Profile / Users / Roles / Permissions / Config / Logs）
- Docker: マルチステージビルド、compose（init-paths / db / web / nginx）、
  `deploy.sh`（stg / prod 自動判定、app / migrate / reset モード）
- ドキュメント運用ルール（CLAUDE.md + docs/ 一式）

## 持ち込まなかったもの（判断）

- アルバム・メディア・バッチ（Celery / Redis）・wiki・certs・Google 連携
- TOTP・パスキー・サービスアカウント（ADR-0002。必要時に photonest から移植）

## 実施中に踏んだ問題

- `duration_ms`（Log.Integer 列）へ float を書き込むと SQLite は型アフィニティで
  float のまま保持し、ログ閲覧 API の Pydantic validation
  （`int_from_float`）が 500 を返した。DB 書き込み前に丸めて解決
  （`db_log_handler.py`）。
