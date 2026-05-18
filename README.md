# fastapitemplate

FastAPI + SQLite のテンプレートです。  
ローカル開発は `uv`、デプロイはそのまま Docker で実行できます。

## 技術スタック

- Python 3.12
- FastAPI (OpenAPI は `/docs` と `/openapi.json`)
- SQLite
- uv (依存管理・実行)
- Docker

## ローカル開発 (uv)

```bash
# uv が未インストールの場合
pip install --user uv

# 依存関係をインストール
uv sync

# 開発サーバー起動
uv run uvicorn main:app --reload
```

アクセス:

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

## API サンプル

```bash
# ヘルスチェック
curl http://127.0.0.1:8000/health

# アイテム作成
curl -X POST http://127.0.0.1:8000/items \
  -H "Content-Type: application/json" \
  -d '{"name":"sample"}'

# アイテム一覧
curl http://127.0.0.1:8000/items
```

SQLite ファイルは実行ディレクトリの `app.db` に作成されます。

## テスト

```bash
uv run pytest
```

## Docker デプロイ

```bash
docker build -t fastapitemplate .
docker run --rm -p 8000:8000 -v $(pwd)/app.db:/app/app.db fastapitemplate
```

Docker 起動後:

- http://127.0.0.1:8000/docs
