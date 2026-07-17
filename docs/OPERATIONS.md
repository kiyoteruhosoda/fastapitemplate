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

- 初期管理者: `admin@example.com` / `admin`
  （`ADMIN_INITIAL_PASSWORD` 環境変数で上書き可。本番では必ず変更する）

## フロントエンドを開発したいとき

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173（/api は 8000 へプロキシ）
```

ビルドして FastAPI から配信させたいとき:

```bash
cd frontend && npm run build     # frontend/dist に出力 → / で配信される
```

## テストを実行したいとき

```bash
uv run pytest                    # smtp マーカーは既定で除外
uv run ruff check .              # Lint
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
make build         # アプリイメージ + dist/image.tar + デプロイスクリプト配置
make build-db      # DB イメージ + dist/image-db.tar
```

## docker compose でローカル起動したいとき

```bash
cp .env.example .env             # 必要に応じて編集
docker compose up -d             # db / web / nginx が起動
```

- アプリ: http://127.0.0.1:8080 （nginx 経由）

## デプロイしたいとき

配置先サーバーの `<app>/<stg|prod>/` に `dist/` の中身
（`image.tar`・`image-db.tar`・`scripts/deploy.sh`）を置いて実行する:

```bash
./scripts/deploy.sh app          # 通常デプロイ（アプリのみ更新）
./scripts/deploy.sh migrate      # DDL 更新時（Alembic migration 追加時）
./scripts/deploy.sh reset        # 完全初期化（DB 消去。破壊的）
```

環境（stg / prod）は配置ディレクトリ名から自動判定される。
`.env` が無ければ初回実行時にテンプレートが自動生成される。

## システム設定を変更したいとき

管理画面（`/admin/config`。要 `admin:system-settings` 権限）から編集する。
保存すると即時反映される（環境変数が設定されているキーは環境変数が優先）。

## ログを確認したいとき

- 画面: `/admin/logs`（要 `system:manage` 権限）
- DB: `log` テーブル（`requestId` でリクエスト単位に追跡）
- コンテナ: `docker compose logs web`
