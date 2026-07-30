# OPERATIONS — 手順書

「〇〇したいとき、〇〇する」の操作手順のみを書く。設計の解説は
`ARCHITECTURE.md`、過去の経緯は `CHANGELOG.md` を参照。

## ローカル開発を始めたいとき

```bash
uv sync                          # 依存関係をインストール
uv run python main.py            # 開発サーバー起動（SQLite: app.db）
```

- API: http://127.0.0.1:8000 / Swagger UI: http://127.0.0.1:8000/docs
- 初回はマイグレーションとマスタデータ投入を行う:

```bash
uv run alembic upgrade head
uv run python scripts/seed_master_data.py
```

- 初期管理者: `admin@example.com` / `admin@example.com`
  （`ADMIN_INITIAL_PASSWORD` 環境変数で上書き可。本番では必ず変更する）

## フロントエンドを開発したいとき

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173（/api は 8000 へプロキシ）
```

ビルドして FastAPI から配信させたいとき:

```bash
cd frontend && npm run build     # frontend/dist に出力 → / で配信される
```

## テストを実行したいとき

```bash
uv run pytest                    # smtp マーカーは既定で除外
cd frontend && npm run test      # Vitest
```

## 品質ゲートを手元で確認したいとき

CI と同じ順序・同じコマンドを流す。落ちたらマージできない（ADR-0006）。

**CI が走るのは PR に対してと `main` への push だけ**（ADR-0009）。PR を作る前の
ブランチ push では走らないので、手元で `make check` を流して確認する。

```bash
make check                       # Backend + Frontend を全部
make check-backend               # Backend だけ
make check-frontend              # Frontend だけ
```

`make check` の中身:

```bash
# Backend
uv run ruff format --check .     # 整形
uv run ruff check .              # 静的解析
uv run mypy                      # 型チェック（対象は pyproject.toml の files）
uv run pytest                    # テスト

# Frontend（cd frontend）
npm run format:check             # 整形（Prettier）
npm run lint                     # 静的解析（ESLint）
npm run type-check               # 型チェック（tsc --noEmit）
npm run test                     # テスト（Vitest）
```

個別に回したいときは `make lint` / `make typecheck` / `make test`、
Frontend は `make lint-frontend` / `make typecheck-frontend` / `make test-frontend`。

## 整形の指摘を自動で直したいとき

```bash
make format                      # Backend + Frontend を自動整形
make format-backend              # ruff format . && ruff check . --fix
make format-frontend             # prettier --write .
```

`ruff check --fix` と `eslint --fix` で直らない指摘は手で直す。

## フロントエンドのテストを書きたいとき

`frontend/src/**/*.test.ts` / `*.test.tsx` に置く（`vite.config.ts` の
`test.include`）。jsdom + Testing Library が使える。

```bash
cd frontend
npm run test:watch               # 変更を監視して再実行
npm run test:coverage            # カバレッジ（coverage/ に出力）
```

## マイグレーションを追加したいとき

1. `shared/infrastructure/models/` のモデルを変更する。
2. マイグレーションを生成・編集する:

```bash
uv run alembic revision --autogenerate -m "<description>"
```

3. 生成ファイル先頭に `from __future__ import annotations` を入れ、
   `upgrade()` / `downgrade()` 双方を確認する。
4. `uv run alembic upgrade head` で適用し、テストで整合性を確認する。

## 設定キーを追加したいとき

以下の3ファイルすべてを更新する（CLAUDE.md「設定管理」参照）:

1. `shared/kernel/settings/system_settings_defaults.py`
2. `shared/kernel/settings/settings.py`
3. `presentation/fastapi/admin/system_settings_definitions.py`

## Docker イメージをビルドしたいとき

```bash
./scripts/build.sh   # アプリ + DB イメージ → dist/（tar・deploy.sh・manifest 一式）
# make build でも同じ（scripts/build.sh を呼ぶだけ）
```

## docker compose でローカル起動したいとき

```bash
cp .env.example .env             # 必要に応じて編集
docker compose up -d             # db / web / nginx が起動
```

- アプリ: http://127.0.0.1:8080 （nginx 経由）

## デプロイしたいとき

配置先サーバーの `<app>/<stg|prod>/` に `dist/` の中身をそのまま置いて実行する:

```bash
./deploy.sh app          # 通常デプロイ（アプリのみ更新）
./deploy.sh migrate      # DDL 更新時（Alembic migration 追加時）
./deploy.sh reset        # 完全初期化（DB 消去。破壊的）
```

環境（stg / prod）は配置ディレクトリ名から自動判定される。
`.env` が無ければ初回実行時にテンプレートが自動生成される。

## デプロイ先に git が無いホスト（Synology 等）で一括デプロイしたいとき

`scripts/build-remote-container.sh` をデプロイ先の `<app>/<stg|prod>/` に一度だけ手で置き、
同じ場所に `build-remote-container.env`（雛形: `scripts/build-remote-container.env.example`）を
作成してから実行する:

```bash
./build-remote-container.sh            # app（通常デプロイ）
./build-remote-container.sh migrate
./build-remote-container.sh reset
```

git pull → build.sh → dist/ 取り込み → deploy.sh を 1 本で実行する
（ビルドは同一ホスト上の dev コンテナ内。スクリプト自身も自動で最新版へ差し替わる）。

## 初回デプロイの WEB 公開ポートを既定値から変えたいとき

`.env` が生成される前（初回デプロイ）にポートを決めるには、`build-remote-container.env` に書く:

```bash
APP_WEB_HOST_PORT=8090
```

初回デプロイ時に生成される `.env` の `WEB_HOST_PORT` へ転記される。
未指定なら環境ディレクトリ名から決まる既定値（stg=8081 / prod=8080）が使われる。

**すでに `.env` がある環境でポートを変えるときは `.env` の `WEB_HOST_PORT` を直接編集する。**
`deploy.sh` は既存の `.env` を書き換えないため、`APP_WEB_HOST_PORT` を後から変えても効かない
（理由は ADR-0008）。編集後は `./deploy.sh app`（または `./build-remote-container.sh`）で再デプロイする。

## システム設定を変更したいとき

管理画面（`/admin/config`。要 `admin:system-settings` 権限）から編集する。
保存すると即時反映される（環境変数が設定されているキーは環境変数が優先）。

「再起動後に反映」と表示される項目（ログ設定・CORS）は保存だけでは効かない。
保存後に出る「今すぐ再起動」を押す（要 `system:manage` 権限）。要求は DB に置かれ、
最大 10 秒でアプリが自分を終了し、コンテナの restart policy で復帰する。

## アプリを再起動したいとき

- 画面: `/admin/config` の再起動ボタン、または `POST /api/admin/system/restart`
- ホスト: `docker compose restart web`

## 管理者がパスワードを忘れてサインインできないとき

メール送信が有効なら `/forgot-password` から再設定する。無効なとき
（`MAIL_ENABLED` が off）は以下のいずれかで復旧する。

> **`scripts/seed_master_data.py` の再実行では復旧しない。** 投入は冪等で既存ユーザーを
> 変更しないため、`ADMIN_INITIAL_PASSWORD` は**ユーザーが存在しないときだけ**使われる。
> 実行は成功するが、パスワードは元のまま。

### 他に `user:manage` を持つユーザーがいるとき

そのユーザーでサインインし、対象ユーザーのパスワードを上書きする。管理画面には
パスワードの項目が無いため、API を直接呼ぶ（Swagger UI `/docs` からも実行できる）。

```bash
curl -X PUT http://127.0.0.1:8000/api/admin/users/<user_id> \
  -H "Authorization: Bearer <access_token>" \
  -H 'Content-Type: application/json' \
  -d '{"password": "<new-password>"}'
```

パスワードは 8 文字以上。対象ユーザーの `<user_id>` は `GET /api/admin/users` または
`/admin/users` の一覧で確認する。

### 管理者が 1 人しかいないとき

対象ユーザーの行を消してから投入スクリプトを流す（消さないと再投入されない）。
`user_roles` と `password_reset_tokens` は `ON DELETE CASCADE` ではないので先に消す
（テーブルの関係は `docs/ER.md`）。

```sql
DELETE FROM user_roles            WHERE user_id IN (SELECT id FROM users WHERE email = 'admin@example.com');
DELETE FROM password_reset_tokens WHERE user_id IN (SELECT id FROM users WHERE email = 'admin@example.com');
DELETE FROM totp_secrets          WHERE user_id IN (SELECT id FROM users WHERE email = 'admin@example.com');
DELETE FROM passkey_credentials   WHERE user_id IN (SELECT id FROM users WHERE email = 'admin@example.com');
DELETE FROM webauthn_challenges   WHERE user_id IN (SELECT id FROM users WHERE email = 'admin@example.com');
DELETE FROM users                 WHERE email = 'admin@example.com';
```

上の SQL を `recover-admin.sql` に保存して流し、続けて初期管理者を作り直す。

```bash
# 開発（SQLite）。sqlite3 コマンドが無ければ
#   python -c "import sqlite3;sqlite3.connect('app.db').executescript(open('recover-admin.sql').read())"
sqlite3 app.db < recover-admin.sql
ADMIN_INITIAL_PASSWORD='<new-password>' uv run python scripts/seed_master_data.py

# docker compose（MariaDB）
docker compose exec -T db \
  mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE" < recover-admin.sql
docker compose exec -e ADMIN_INITIAL_PASSWORD='<new-password>' web \
  python scripts/seed_master_data.py
```

作り直したユーザーの ID は `master_data.DEFAULT_ADMIN_ID`（= 1）で固定されるため、
`admin` ロールの付与も含めて元の状態に戻る。二要素認証・パスキーの登録は消える。

## 二要素認証・パスキーを設定したいとき

利用者自身が `/security`（プロフィール → セキュリティ）から操作する。

- 二要素認証: 「設定する」→ 認証アプリで QR を読む → 表示されたコードを入力して確定。
  確定するまで有効にならないため、途中でやめてもログインできなくなることはない。
- パスキー: 「パスキーを追加」→ 端末の画面ロック／セキュリティキーで承認。

パスキーを使う前に `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` を実際に開く URL へ合わせる
（`.env.example` 参照）。RP ID を後から変えると登録済みのパスキーは使えなくなる。

| 開き方 | `WEBAUTHN_RP_ID` | `WEBAUTHN_ORIGIN` |
|---|---|---|
| `npm run dev`（既定） | `localhost` | `http://localhost:5173` |
| ビルド済み SPA を FastAPI から | `localhost` | `http://localhost:8000` |
| docker compose（nginx 経由） | `localhost` | `http://localhost:8080` |
| 本番 | 公開ドメイン | `https://<公開ドメイン>` |

RP ID にはドメイン名しか指定できない（IP アドレス不可）。開発時は
`127.0.0.1` ではなく `localhost` で開くこと。

## ログを確認したいとき

| 見たいもの | 画面（必要 scope） | DB | コンテナ |
|---|---|---|---|
| システムが何をしたか（リクエスト・警告・例外） | `/admin/logs`（`log:view`） | `log` | `docker compose logs web` |
| 誰が何をしたか（ログイン・管理操作・設定変更） | `/admin/audit-logs`（`audit:view`） | `audit_log` | — |

どちらの記録にも同じ `requestId` が入る。片方で見つけた ID をもう一方の絞り込みに
入れると、1 リクエストの記録を両側から突き合わせられる。画面ごとの絞り込み手順は
`frontend/README.md`「操作マニュアル」を参照。

API から直接引くときは Swagger UI（`/docs`）の `GET /api/admin/logs` /
`GET /api/admin/audit-logs` を使う。

### DB へ書くログの量を減らしたいとき

1. `/admin/config` の「ログ」カテゴリを開く。
2. `LOG_DB_MIN_LEVEL` を `WARNING` 等に上げて保存する（再起動は不要）。

stdout 側の出力は `LOG_LEVEL` のままなので、コンテナのログには従来どおり出る。
DB への書き込みを完全に止めるなら `LOG_TO_DATABASE` を off にする（要再起動）。
監査ログはこの設定の影響を受けない（常に記録される）。

### 監査ログの接続元 IP が nginx のアドレスになるとき

`/admin/config` の「一般」カテゴリの `TRUSTED_PROXY_HOPS` に、アプリの前に置いて
いる**信頼できる**リバースプロキシの段数を設定する（同梱の docker-compose 構成は
`1`、設定済み）。

0（既定）のあいだは `X-Forwarded-For` を一切見ない。このヘッダーは送信元が自由に
付けられるため、段数を宣言していない状態で採用すると任意の IP を監査ログへ記録
させられる。アプリをプロキシ無しで直接公開している場合は 0 のままにする。

判定はアプリだけが行う。Gunicorn / Uvicorn 側の転送ヘッダー処理は
`--forwarded-allow-ips=""`（`scripts/entrypoint.sh`）と `proxy_headers=False`
（`main.py`）で切ってある。**自前で起動コマンドを書くときも同じ指定を入れること。**
外すと、サーバー層が `X-Forwarded-For` の左端（＝詐称できる値）で接続元を
書き換えてしまい、この設定が効かなくなる。

### ログを DB から消したいとき

自動削除は入っていない。`log` が増えすぎた場合は期間を指定して削除する。

```sql
DELETE FROM log WHERE created_at < '2026-01-01';
```

`audit_log` は監査記録であり、消す前に保持要件を確認すること。
