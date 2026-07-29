# scripts — 現在の仕様

| スクリプト | 役割 |
|---|---|
| `entrypoint.sh` | コンテナ起動。起動診断 → DB 接続待ち（MariaDB 使用時）→ `web` モードでは `alembic upgrade head` の後に Gunicorn + UvicornWorker を起動する。モードは compose の `command`（`web` / `migrate`）で指定する。 |
| `run_db_migrations.py` | `alembic upgrade head` を実行する。entrypoint / deploy から共用。どこから呼んでもプロジェクトルートへ chdir して動く。 |
| `seed_master_data.py` | ロール・権限・初期管理者を投入する（冪等）。値の正本は `shared/domain/auth/master_data.py`。`ADMIN_INITIAL_PASSWORD` 環境変数で初期管理者パスワードを上書きできる。 |
| `generate_version.sh` | `shared/kernel/version.json` を Git 情報から生成する（ローカル確認用。Docker ビルドでは Dockerfile の ARG から生成される）。 |
| `build.sh` | ソース側でのビルド。アプリ + DB イメージをビルドし、`dist/` にデプロイバンドル（`image.tar`・`image-db.tar`・`deploy.sh`・`.env.example`・`manifest.env`・`manifest.sha256`）を書き出す。`make build` はこれを呼ぶだけ。`PLATFORM=linux/amd64` でクロスビルド（要 buildx）。 |
| `deploy.sh` | 配置先サーバーでのデプロイ。配置ディレクトリ名（`stg` / `prod` 系）から環境を自動判定し、`app` / `migrate` / `reset` の3モードを持つ。`.env` が無ければテンプレートを自動生成する。compose と nginx 設定はロードしたイメージ内のコピーへ常に同期される。 |
| `build-remote-container.sh` | git 非搭載のデプロイ先向けの一括デプロイ（SYNC → BUILD → PICK → DEPLOY）。同一ホスト上の dev コンテナ内で git pull と `build.sh` を実行し、生成された `dist/` をデプロイ先へ取り込んで `deploy.sh` を実行する。手置きのブートストラップだが、実行のたびに dev コンテナ内の最新版と比較して自分自身を自動更新する。設定はスクリプトと同じ場所の `build-remote-container.env`（雛形: `build-remote-container.env.example`）。 |

## deploy.sh の挙動

- 配置は `dist/` の中身をそのまま `<app>/<stg|prod>/` へ展開した形のみ
  （`deploy.sh` が環境ディレクトリ直下にある前提で動く）。
- イメージは `image.tar`（`scripts/build.sh` の成果物）を `docker load` し、
  環境別タグ（`fastapitemplate:stg` 等）を付け直す。stg / prod を同一ホストで
  運用してもイメージを取り合わない。
- `manifest.env` / `manifest.sha256` があれば、tar の checksum 検証（転送破損検出）と
  ロード済みイメージ ID の照合（一致すれば `docker load` を省略）を行う。無ければ
  従来どおり動く。
- `reset` は `mnt/db_data` と `mnt/data` を削除する破壊的操作。DB イメージ
  （`image-db.tar`）もこのとき再ロードされる。
- ヘルスチェックは `http://127.0.0.1:<WEB_HOST_PORT>/healthz`。失敗時は
  各コンテナのログを出力して終了する。
