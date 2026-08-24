# scripts — 現在の仕様

| スクリプト | 役割 |
|---|---|
| `entrypoint.sh` | コンテナ起動。起動診断 → DB 接続待ち（MariaDB 使用時）→ `web` モードでは `alembic upgrade head` の後に Gunicorn + UvicornWorker を起動する。モードは compose の `command`（`web` / `migrate`）で指定する。 |
| `run_db_migrations.py` | `alembic upgrade head` を実行する。どこから呼んでもプロジェクトルートへ chdir して動く。 |
| `seed_master_data.py` | ロール・権限・初期管理者を投入する（冪等）。値の正本は `shared/domain/auth/master_data.py`。`ADMIN_INITIAL_PASSWORD` 環境変数で初期管理者パスワードを上書きできる。 |
| `generate_pwa_icons.py` | `frontend/public/` のアイコン（`favicon.svg`・`pwa-192x192.png`・`pwa-512x512.png`・`pwa-maskable-512x512.png`・`apple-touch-icon.png`）を生成する。配色と図形の正本はこのスクリプトで、出力物は生成結果としてコミットする。PNG の書き出しは標準ライブラリ（`zlib` / `struct`）だけで行うため追加の依存は要らない。`maskable` 用は OS の切り抜きに備えてセーフゾーンを取った別画像、`apple-touch-icon.png` は iOS が独自に角丸へ切るため透明な角を持たない。 |
| `generate_version.sh` | `shared/kernel/version.json` を作る。**ビルドの前に走らせる**（Komodo Build の `pre_build`／`make image`）。詳細は下記。 |

## generate_version.sh — 版の刻印

`/info`・システムステータス画面・起動ログが「どのコミットのイメージが動いているか」を
答えるための唯一の出どころ。**Docker ビルドの前にコンテキストへ置く**方式に一本化して
ある（ADR-0023）。

| 呼ばれる場所 | 何が起きるか |
|---|---|
| Komodo Build の `pre_build` | クローン済みリポジトリで git から生成する。**本番の経路。** |
| `Dockerfile` の `RUN` | 上で生成済みなら**何もしない**。無ければ `dev` と刻む |
| `make image` / 直接実行 | 手元の git から生成する |

優先順位は **既にある `version.json` ＞ git ＞ `dev`**。既存の内容は決して上書きしない
（上書きにすると `pre_build` が作った本物の版を Dockerfile 側が `dev` に潰す）。

- 生成物 `shared/kernel/version.json` は **`.gitignore` 済み**。コミットするとその内容が
  常に優先され、どのイメージも同じ古い版を名乗り続ける。
- `git -c safe.directory=*` を付けている。Komodo の periphery はクローンした所有者と
  別 UID で `pre_build` を走らせることがあり、無いと "dubious ownership" で git が黙って
  落ちて `dev` になる。
- detached HEAD（CI のチェックアウト等）でブランチ名が取れないときは `BRANCH_OVERRIDE` で補える。
