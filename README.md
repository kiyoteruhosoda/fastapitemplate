# fastapitemplate

FastAPI + DDD のアプリケーションテンプレートです（photonest の構成・設計思想がベース）。
認証認可（JWT + scope）・システム設定管理・構造化ログ・管理画面 SPA・
Docker と Komodo へのデプロイ定義まで含んだ状態から開発を始められます。

## 技術スタック

- Python 3.12 / uv（依存管理）
- FastAPI + Pydantic（OpenAPI は `/docs`・`/openapi.json`）
- SQLAlchemy 2.x + Alembic（本番 MariaDB 10.11 / 開発・テスト SQLite）
- React + TypeScript + Vite（`frontend/`、SPA スケルトン。i18n・テーマ切り替え込み）
- Docker（db / app / front 構成）+ Gunicorn + UvicornWorker
- 品質ゲート: Ruff / MyPy（strict）/ PyTest ・ Prettier / ESLint / TypeScript / Vitest

## 主な機能

- JWT 認証（access / refresh）・パスワード変更・パスワードリセット（SMTP）
- **二要素認証（TOTP）とパスキー（WebAuthn）**（`bounded_contexts/account_security/`）
- **scope（権限コード）ベースの認可**（ユーザー / ロール / 権限の管理 API + 画面）
- システム設定（優先順位: 環境変数 > DB > デフォルト。管理画面から編集可）
- 起動時にしか読まれない設定を反映するための**アプリ自己再起動**
- **日英の言語切り替えとテーマ切り替え**（ライト / ダーク / OS 追従）
- 構造化ログ（JSON stdout + `log` テーブル。`requestId` で追跡）と、
  **監査ログ**（`audit_log`。誰が何をしたか）。どちらも管理画面から検索・絞り込みできる
  （`bounded_contexts/audit/`）
- 運用プローブ（`/healthz` `/readyz` `/info`）+ Prometheus `/metrics`
- `bounded_contexts/example/`（Item CRUD）= 新しい機能を追加するときの見本

## クイックスタート（ローカル開発）

```bash
uv sync
uv run alembic upgrade head          # スキーマ + マスタデータ（SQLite: app.db）
uv run python main.py                # http://127.0.0.1:8000
```

- Swagger UI: http://127.0.0.1:8000/docs
- 初期管理者: `admin@example.com` / `admin@example.com`（`ADMIN_INITIAL_PASSWORD` で上書き可）

フロントエンド:

```bash
cd frontend && npm install && npm run dev    # http://localhost:5173（/api をプロキシ）
```

パスキーを試す場合は **`localhost` で開く**（`127.0.0.1` ではない）。WebAuthn の
RP ID はドメイン名でなければならず IP アドレスは使えないため、既定値は
`localhost` になっている。

## 品質ゲート（テスト・Lint・型チェック）

CI の必須ゲートを手元で流す。落ちたらマージできない（[ADR-0006](docs/decisions/ADR-0006-quality-gates.md)）。

```bash
make check              # Backend + Frontend の 8 ゲートすべて
make format             # 整形の指摘を自動修正
```

| 対象 | ゲート |
|---|---|
| Backend | Ruff Format → Ruff Check → MyPy（strict）→ PyTest |
| Frontend | Prettier → ESLint → TypeScript → Vitest |

個別に回すときは `make check-backend` / `make check-frontend`、
さらに `make lint` / `make typecheck` / `make test`（Frontend は `*-frontend`）。

## Docker / デプロイ

**ビルドとデプロイは Komodo（nolumialab）で行います。成果物はコンテナイメージです**
（[ADR-0023](docs/decisions/ADR-0023-komodo-build-and-deploy.md)）。

```
GitHub のソース ──push──▶ Komodo Build ──push──▶ hub.nolumia.com:5000/komodo/<app>
                                                  ＝ 成果物（タグ: latest / <コミット> / 0.0.N）
                                                            │ pull
                      deploy-repo ──ResourceSync──▶ Komodo Stack ──┘
```

手元で動かすときは compose を使います（デプロイには使いません）。

```bash
make image                      # Dockerfile が壊れていないかの確認用ビルド
cp .env.example .env
docker compose up -d            # db / app / front が起動 → http://127.0.0.1:8080
```

デプロイ定義の雛形（compose・Komodo の Build / Stack 定義）は
[deploy/komodo/](deploy/komodo/README.md) に入っています。deploy-repo へ複製して使います。

**このテンプレートから作ったプロジェクトは名前を変えてください。** イメージ名・
スタック名・ネットワーク別名・データディレクトリがその名前から派生します。
`fastapitemplate` のまま Komodo に登録すると、テンプレート由来の別プロジェクトと
イメージとエイリアスを取り合います。

**`pyproject.toml` の `[project].name` も同時に変えてください。** ここがアプリ自身の
名前の正本で、Swagger の題と、外へ出るときに名乗る `User-Agent` がここから導かれます
（[ADR-0031](docs/decisions/ADR-0031-the-app-name-comes-from-pyproject.md)）。
コード側に名前を直に書かないでください。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 設計ルール・制約事項・ドキュメント運用（作業テンプレ） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | レイヤー構成・DDD パターン解説 |
| [docs/ER.md](docs/ER.md) | ER 図・テーブル定義 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 操作手順書 |
| [docs/Progress.md](docs/Progress.md) | 進行中タスク |
| [docs/decisions/](docs/decisions/) | 設計判断（ADR） |
| [deploy/komodo/README.md](deploy/komodo/README.md) | Komodo でのビルドとデプロイ（定義の雛形つき） |
| [frontend/README.md](frontend/README.md) | 画面遷移図・画面仕様・操作マニュアル |

## ライセンス

[LICENSE](LICENSE) を参照。
