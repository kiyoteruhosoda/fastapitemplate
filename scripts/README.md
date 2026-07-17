# scripts — 現在の仕様

| スクリプト | 役割 |
|---|---|
| `entrypoint.sh` | コンテナ起動。起動診断 → DB 接続待ち（MariaDB 使用時）→ `web` モードでは `alembic upgrade head` の後に Gunicorn + UvicornWorker を起動する。モードは compose の `command`（`web` / `migrate`）で指定する。 |
| `run_db_migrations.py` | `alembic upgrade head` を実行する。entrypoint / deploy から共用。どこから呼んでもプロジェクトルートへ chdir して動く。 |
| `seed_master_data.py` | ロール・権限・初期管理者を投入する（冪等）。値の正本は `shared/domain/auth/master_data.py`。`ADMIN_INITIAL_PASSWORD` 環境変数で初期管理者パスワードを上書きできる。 |
| `generate_version.sh` | `shared/kernel/version.json` を Git 情報から生成する（ローカル確認用。Docker ビルドでは Dockerfile の ARG から生成される）。 |
| `deploy.sh` | 配置先サーバーでのデプロイ。配置ディレクトリ名（`stg` / `prod`）から環境を自動判定し、`app` / `migrate` / `reset` の3モードを持つ。`.env` が無ければテンプレートを自動生成する。compose と nginx 設定はロードしたイメージ内のコピーへ常に同期される。 |

## deploy.sh の挙動

- イメージは `dist/image.tar`（`make build` の成果物）を `docker load` し、
  環境別タグ（`fastapitemplate:stg` 等）を付け直す。stg / prod を同一ホストで
  運用してもイメージを取り合わない。
- `reset` は `mnt/db_data` と `mnt/data` を削除する破壊的操作。DB イメージ
  （`dist/image-db.tar`）もこのとき再ロードされる。
- ヘルスチェックは `http://127.0.0.1:<WEB_HOST_PORT>/healthz`。失敗時は
  各コンテナのログを出力して終了する。
