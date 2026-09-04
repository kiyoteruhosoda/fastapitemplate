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

## アプリのアイコン（PWA・favicon）を変えたいとき

配色（`GRADIENT_START` / `GRADIENT_END`）と図形（`MARK_POINTS`）を
`scripts/generate_pwa_icons.py` で編集してから生成し直す。出力物もコミットする。

```bash
uv run python scripts/generate_pwa_icons.py   # frontend/public/ の 5 ファイルを再生成
```

図形を変えたときは `frontend/index.html` の `theme-color` と
`frontend/vite.config.ts` の `theme_color`（どちらも `#4f46e5`）も配色に合わせる。

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

## Docker イメージを手元でビルドしたいとき

```bash
make image           # scripts/generate_version.sh → docker build -t fastapitemplate:dev .
```

**手元での確認用**（Dockerfile が壊れていないか）。デプロイに使う成果物は Komodo が
焼いてレジストリへ push する（ADR-0023）。

## docker compose でローカル起動したいとき

```bash
make image                       # 先にイメージを作る（fastapitemplate:dev）
cp .env.example .env             # 必要に応じて編集
docker compose up -d             # db / app / front が起動
```

- アプリ: http://127.0.0.1:8080 （front＝nginx 経由）

ホストへ公開されるのは `front` だけ。`app` と `db` は Docker ネットワーク内部からのみ
到達できる（ADR-0010）。

**この compose はローカル開発専用。** デプロイ先の compose は
`deploy/komodo/compose.yaml`（deploy-repo の `stacks/<app>/compose.yaml`）。
サービス名・ネットワーク別名・nginx 設定は両者で揃えてある。

## DB を操作したいとき（SQL を流す・ダンプを取る）

`db` はホストにポートを持たないため、`docker compose exec` でコンテナ内から実行する。

**資格情報は必ず `sh -c '…'`（シングルクォート）でコンテナ内に展開させる。**
`.env` は既定では資格情報の行がコメントアウトされていて（値は compose の
`${VAR:-default}` が供給する）、ホスト側のシェルには変数が無い。ダブルクォートで
書くとホストで空文字に展開され、パスワードなしで接続を試みて失敗する。

```bash
# 対話シェル
docker compose exec db sh -c 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"'

# SQL ファイルを流す（-T でホストの標準入力を渡す。リダイレクトはホスト側で解決される）
docker compose exec -T db \
  sh -c 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' < some.sql

# ダンプを取る（出力はホスト側のファイルへ）
docker compose exec -T db \
  sh -c 'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' > dump.sql
```

デプロイ先（Komodo）では compose プロジェクトがスタック名で分かれている。
nolumialab 上で `docker compose -p <スタック名> exec ...` として実行する。

## DB へホストのツールから一時的につなぎたいとき

GUI クライアントを使いたい場合だけ、その場限りのポートフォワード用コンテナを立てる。
`docker-compose.yml` は変更しない（恒久的に開けないため。ADR-0010）。

```bash
# ネットワーク名は .env の DOCKER_NETWORK_NAME（未設定ならリポジトリ名）
docker run --rm -it --network "$(grep -E '^DOCKER_NETWORK_NAME=' .env | tail -n1 | cut -d= -f2-)" \
  -p 127.0.0.1:3307:3306 alpine/socat \
  tcp-listen:3306,fork,reuseaddr tcp-connect:db:3306
```

`127.0.0.1:3307` へつなげば DB に到達する。**作業が終わったら Ctrl-C で止める**
（コンテナを消すと公開ポートも消える）。

## デプロイしたいとき

**Komodo（https://komodo.nolumia.com）から行う。** 手順の正本は deploy-repo の
`docs/new-stack.md`、このテンプレート固有の点は `deploy/komodo/README.md`（ADR-0023）。

```
1. ソースを push        → Komodo Build がイメージを焼いてレジストリへ push
                          （webhook を付けていなければ Komodo の画面から Build を実行）
2. Komodo の画面で対象スタックを Deploy   → 新しいイメージを pull して入れ替わる
3. 疎通確認  curl -s -o /dev/null -w '%{http_code}\n' http://10.10.2.11:<PORT>/healthz
```

**本番スタックの入れ替えは自動化していない。** push のたびに本番が差し替わるのを
避けるため、ビルドと定義同期までを自動にしてある。

マイグレーションは `app` の entrypoint が起動時に流す（`alembic upgrade head`）。
デプロイの手順としては分かれていない。

## デプロイした版を確認したいとき

```bash
curl -s http://10.10.2.11:<PORT>/info        # version / commit / branch / build_date
```

`version` が `dev` になっている場合、その Build 定義に `pre_build` が無い
（`deploy/komodo/README.md`「pre_build（版の刻印）」）。ビルドは成功するのに版だけが
分からない状態なので、気付いたら Build 定義を直して焼き直す。

## 前の版へ戻したいとき

Komodo はビルドのたびに `latest` / `<コミット>` / `0.0.N` のタグを打つ。
戻したい版のタグをスタックの `APP_IMAGE_TAG` に指定して Deploy する。

```toml
APP_IMAGE_TAG = a3817d5      # deploy-repo の resources/stacks.toml
```

**DB のスキーマは戻らない。** マイグレーションを含む版から戻すときは、
その `downgrade()` を先に当てる必要がある。

## 新しいアプリを Komodo に載せたいとき

`deploy/komodo/` の雛形を deploy-repo へ複製する。手順は
[deploy/komodo/README.md](../deploy/komodo/README.md)。要点だけ:

- ポートは採番表から**計算**する（空き番号を勝手に取らない）
- `builds.toml` の `[build.config.pre_build]` を**必ず書く**（版の刻印）
- `stacks.toml` に `tags = ["managed"]` と `ignore_services = ["init-paths"]`
- 秘密は Komodo の Variable へ。`JWT_SECRET_KEY` は必ず生成した値を入れる
- 公開するときは **Access を作ってから ingress**（逆順は無認証で公開される）

## システム設定を変更したいとき

管理画面（`/admin/config`。要 `admin:system-settings` 権限）から編集する。
保存すると即時反映される（環境変数が設定されているキーは環境変数が優先）。

「再起動後に反映」と表示される項目（ログ設定・CORS）は保存だけでは効かない。
保存後に出る「今すぐ再起動」を押す（要 `system:manage` 権限）。要求は DB に置かれ、
最大 10 秒でアプリが自分を終了し、コンテナの restart policy で復帰する。

## アプリを再起動したいとき

- 画面: `/admin/config` の再起動ボタン、または `POST /api/admin/system/restart`
- ホスト: `docker compose restart app`（デプロイ先は Komodo の画面から）

## API を curl や CI から叩きたいとき

トークンは応答本文に載らず **Cookie で運ばれる**（ADR-0028）。Cookie を保持して叩く。

```bash
# ログイン（Cookie をファイルへ保存する）
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"admin@example.com"}'

# 読み取りは Cookie だけでよい
curl -b cookies.txt http://127.0.0.1:8000/api/auth/me

# 更新系は CSRF の二重送信トークンが要る（cookies.txt から読む）
CSRF=$(awk '$6=="csrf_token" {print $7}' cookies.txt)
curl -b cookies.txt -X PUT http://127.0.0.1:8000/api/auth/me \
  -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","username":"admin"}'
```

既にトークンを持っている呼び出し元は `Authorization: Bearer <token>` でも叩ける。
**その場合 CSRF トークンは要らない**（ヘッダーは自動では送られないため）。

Swagger UI（`/docs`）は同一オリジンなので、**ブラウザでログインしていればそのまま
叩ける**（Authorize ボタンは使わない）。

## SSO（外部 IdP との連携）を有効にしたいとき

1. IdP にクライアントを登録する。折り返し先は `<APP_BASE_URL>/api/auth/sso/callback`。
   自前 idp（assay）なら管理 API で登録できる。

   ```bash
   curl -X POST "$ISSUER/admin/clients" -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"app_name":"<アプリ名>","client_type":"confidential",
          "redirect_uris":["https://<ホスト>/api/auth/sso/callback"],
          "scopes":["openid","profile","email"],
          "token_endpoint_auth_method":"private_key_jwt","jwks":"<公開鍵の JWKS>"}'
   ```

2. 設定を入れる（環境変数か管理画面 > システム設定 > SSO）。

   ```
   OIDC_ENABLED=true
   OIDC_ISSUER=<発行者 URL>
   OIDC_CLIENT_ID=<登録で得た client_id>
   OIDC_CLIENT_AUTH_METHOD=client_secret_basic   # または private_key_jwt
   OIDC_CLIENT_SECRET=<client_secret_basic のとき>
   OIDC_REDIRECT_URI=https://<ホスト>/api/auth/sso/callback
   ```

3. 起動時のログで `sso_ready` を確かめる。`sso_disabled_by_configuration` なら
   設定が欠けている。`sso_private_key_unreadable` なら鍵が読めていない。

## SSO で `private_key_jwt` を使いたいとき

1. 秘密鍵（PEM）をホストへ置き、コンテナへ **read-only** で渡す。
2. 設定に**在り処**だけを入れる（鍵そのものは設定にも DB にも入れない）。

   ```
   OIDC_CLIENT_AUTH_METHOD=private_key_jwt
   OIDC_PRIVATE_KEY_FILE=/run/oidc/client.key
   OIDC_PRIVATE_KEY_KID=<IdP に複数鍵があるときだけ>
   ```

⚠ **ファイルとディレクトリの両方**でコンテナの実行 gid が通ること。ディレクトリに
実行ビットが無いと、起動も設定画面も通るのに**利用者が IdP から戻ってきた瞬間だけ**
落ちる。起動時のログ（`sso_ready` / `sso_private_key_unreadable`）で確かめる。

## 強い認証を IdP に要求したいとき

`OIDC_ACR_VALUES` に IdP の予約語を入れる（自前 idp なら `urn:assay:ac:mfa`）。

```
OIDC_ACR_VALUES=["urn:assay:ac:mfa"]
```

⚠ **入れたら fail closed になる。** 返ってきた `acr` が要求と一致しなければ、
また `acr` が返ってこなければ、ログインを断る（`sso_acr_not_satisfied`）。
予約語を持たない IdP へつないでいるときは**空のままにする**。

## パスワードでのログインを止めたいとき（SSO 専用にする）

```
LOCAL_LOGIN_ENABLED=false
```

パスワード・パスキーでのログインと、ローカル資格情報の登録（パスキー・TOTP・
パスワード変更）が 403 `local_login_disabled` になる。ログイン画面はパスワード欄と
パスキーのボタンを出さなくなる。

⚠ **締め出しの経路がある。** この状態で IdP が落ちる、あるいは最後の管理者が IdP 側で
止まると誰も入れなくなる。**復旧は環境変数で `LOCAL_LOGIN_ENABLED=true` へ戻して
再起動する**（環境変数は DB の設定より優先されるので、管理画面に入れなくても戻せる）。

## 管理者がパスワードを忘れてサインインできないとき

メール送信が有効なら `/forgot-password` から再設定する。無効なとき
（`MAIL_ENABLED` が off）は以下のいずれかで復旧する。

> **`scripts/seed_master_data.py` の再実行では復旧しない。** 投入は冪等で既存ユーザーを
> 変更しないため、`ADMIN_INITIAL_PASSWORD` は**ユーザーが存在しないときだけ**使われる。
> 実行は成功するが、パスワードは元のまま。
>
> ⚠ **マイグレーションは初期管理者を作らない**（ADR-0024。据え付けの `0002` だけが
> 作る）。消した `admin@example.com` は消えたままになる。据え直したいときは、
> このスクリプトを手で流す。

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

# docker compose（MariaDB）。資格情報はコンテナ内で展開させる（上記「DB を操作したいとき」参照）
docker compose exec -T db \
  sh -c 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' < recover-admin.sql
docker compose exec -e ADMIN_INITIAL_PASSWORD='<new-password>' app \
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
| docker compose（front＝nginx 経由） | `localhost` | `http://localhost:8080` |
| 本番 | 公開ドメイン | `https://<公開ドメイン>` |

RP ID にはドメイン名しか指定できない（IP アドレス不可）。開発時は
`127.0.0.1` ではなく `localhost` で開くこと。

## ログを確認したいとき

| 見たいもの | 画面（必要 scope） | DB | コンテナ |
|---|---|---|---|
| システムが何をしたか（リクエスト・警告・例外） | `/admin/logs`（`log:view`） | `log` | `docker compose logs app` |
| 誰が何をしたか（ログイン・管理操作・設定変更） | `/admin/audit-logs`（`audit:view`） | `audit_log` | — |

どちらの記録にも同じ `requestId` が入る。片方で見つけた ID をもう一方の絞り込みに
入れると、1 リクエストの記録を両側から突き合わせられる。画面ごとの絞り込み手順は
`frontend/README.md`「操作マニュアル」を参照。

エラーだけを見たいときは `/admin/logs` のレベルで絞る（**5xx は ERROR、4xx は
WARNING**、401 は INFO）。`/healthz`・`/readyz`・`/api/health`・`/metrics` の成功した
アクセスは記録されない（失敗したときは記録される）。

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

### 古いログを自動で消したいとき

保持日数を設定すると、その日数より古い行が定期的に（6 時間ごと・起動直後にも 1 回）
削除される。**既定は `0` で、どちらのテーブルも消えない。**

1. `/admin/config` の「ログ」カテゴリを開く。
2. 残したい日数を入れて保存する（再起動は不要。次の周回から効く）。

| 設定キー | 対象 | 既定 |
|---|---|---|
| `LOG_RETENTION_DAYS` | `log`（アプリログ） | `0`（削除しない） |
| `AUDIT_LOG_RETENTION_DAYS` | `audit_log`（監査ログ） | `0`（削除しない） |

`0` に戻せば削除は止まる。**消した行は復元できない。** 監査ログに日数を入れる前に、
保持要件（法令・社内規程）を確認すること。

削除した行数は `/admin/logs` に INFO で残る（`保持期間を過ぎたログを削除しました`）。
何も消さなかった回は記録されない。

### ログを DB から今すぐ消したいとき

保持日数の設定を待たずに消す場合は、期間を指定して削除する。

```sql
DELETE FROM log WHERE created_at < '2026-01-01';
DELETE FROM audit_log WHERE occurred_at < '2026-01-01';
```

`audit_log` は監査記録であり、消す前に保持要件を確認すること。
