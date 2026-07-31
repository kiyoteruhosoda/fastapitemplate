# scripts — 現在の仕様

| スクリプト | 役割 |
|---|---|
| `entrypoint.sh` | コンテナ起動。起動診断 → DB 接続待ち（MariaDB 使用時）→ `web` モードでは `alembic upgrade head` の後に Gunicorn + UvicornWorker を起動する。モードは compose の `command`（`web` / `migrate`）で指定する。 |
| `run_db_migrations.py` | `alembic upgrade head` を実行する。entrypoint / deploy から共用。どこから呼んでもプロジェクトルートへ chdir して動く。 |
| `seed_master_data.py` | ロール・権限・初期管理者を投入する（冪等）。値の正本は `shared/domain/auth/master_data.py`。`ADMIN_INITIAL_PASSWORD` 環境変数で初期管理者パスワードを上書きできる。 |
| `generate_pwa_icons.py` | `frontend/public/` のアイコン（`favicon.svg`・`pwa-192x192.png`・`pwa-512x512.png`・`pwa-maskable-512x512.png`・`apple-touch-icon.png`）を生成する。配色と図形の正本はこのスクリプトで、出力物は生成結果としてコミットする。PNG の書き出しは標準ライブラリ（`zlib` / `struct`）だけで行うため追加の依存は要らない。`maskable` 用は OS の切り抜きに備えてセーフゾーンを取った別画像、`apple-touch-icon.png` は iOS が独自に角丸へ切るため透明な角を持たない。 |
| `generate_version.sh` | `shared/kernel/version.json` を Git 情報から生成する（ローカル確認用。Docker ビルドでは Dockerfile の ARG から生成される）。 |
| `build.sh` | ソース側でのビルド。アプリ + DB イメージをビルドし、`dist/` にデプロイバンドル（`image.tar`・`image-db.tar`・`deploy.sh`・`.env.example`・`manifest.env`・`manifest.sha256`）を書き出す。`make build` はこれを呼ぶだけ。`PLATFORM=linux/amd64` でクロスビルド（要 buildx）。 |
| `deploy.sh` | 配置先サーバーでのデプロイ。配置ディレクトリ名（`stg` / `prod` 系）から環境を自動判定し、`app` / `migrate` / `reset` の3モードを持つ。`.env` が無ければテンプレートを自動生成する。compose と nginx 設定はロードしたイメージ内のコピーへ常に同期される。 |
| `build-remote-container.sh` | git 非搭載のデプロイ先向けの一括デプロイ（SYNC → BUILD → PICK → DEPLOY）。同一ホスト上の dev コンテナ内で git pull と `build.sh` を実行し、生成された `dist/` をデプロイ先へ取り込んで `deploy.sh` を実行する。手置きのブートストラップだが、実行のたびに dev コンテナ内の最新版と比較して自分自身を自動更新する。設定はスクリプトと同じ場所の `build-remote-container.env`（雛形: `build-remote-container.env.example`）。`APP_WEB_HOST_PORT` を書くと、初回デプロイで生成される `.env` の `WEB_HOST_PORT` へ転記される。 |

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
- WEB 公開ポートの優先順位は `.env` の `WEB_HOST_PORT` ＞ 環境変数 `APP_WEB_HOST_PORT`
  ＞ 環境ディレクトリ名由来の既定値（stg=8081 / prod=8080）。解決した値は compose へ
  `export` されるため、公開ポートとヘルスチェック URL は常に一致する（ADR-0008）。
  `APP_WEB_HOST_PORT` が不正な値のときデプロイを中断するのは、それが実際に選ばれたとき
  （`.env` に `WEB_HOST_PORT` が無いとき）だけ。使われない場合は警告のみで続行する。
- 停止は `docker compose down --remove-orphans`。その後 `up` の前に、このデプロイが
  作るコンテナ名（`<プロジェクト>-<サービス>-1` と `.env` の `DB_CONTAINER_NAME`）を
  握っている残骸があれば消す。`up` が名前衝突で落ちた場合も、エラーメッセージから
  相手のコンテナ ID を取り出して消し、1 度だけやり直す。消すのは compose の
  プロジェクトラベルが自分と同じか、ラベルを持たないものだけ。別プロジェクトの
  コンテナが名前を握っている場合は消さずに中断する（ADR-0014）。
- 削除できたかは `docker rm -f` の終了コードでは判定しない。コンテナが存在しなくても
  成功で返るため、出力が `No such container` なら「実体は無いが名前は握られたまま」と
  みなす。この状態は再試行では解消しないので、やり直さずデーモンの再起動を促して
  中断する。やり直した `up` が前回と同じコンテナ ID と衝突した場合も同じ扱い。
- デーモンの再起動を促すのは上記の「実体が無い」と分かったときだけ。削除がそれ以外の
  理由（認可プラグインによる拒否・ストレージやデーモンの一時的なエラー等）で失敗した
  場合は、原因が別なので実際のメッセージをそのまま見せ、通常どおりモジュールログ付きの
  診断を出して終わる。
- ヘルスチェックは `http://127.0.0.1:<WEB_HOST_PORT>/healthz`。失敗時は
  各コンテナのログと、上記コンテナ名の現在の持ち主を出力して終了する。
