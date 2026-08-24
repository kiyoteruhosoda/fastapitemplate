# Komodo へのデプロイ

このテンプレートから作ったアプリを nolumialab の Komodo で**ビルドして動かす**ための
定義一式。ビルドとデプロイの方式そのものは [ADR-0023](../../docs/decisions/ADR-0023-komodo-build-and-deploy.md)。

```
GitHub のソース ──push──▶ Komodo Build ──push──▶ hub.nolumia.com:5000/komodo/<app>
                          （nolumialab）          ＝ 成果物（コンテナイメージ）
                                                            │ pull
deploy-repo（稼働状態の正）──ResourceSync──▶ Komodo Stack ──┘
```

**成果物はレジストリのイメージ**で、タグは `latest` / `<コミット>` / `0.0.N` の 3 系統が付く。
戻すときはコミットのタグを `APP_IMAGE_TAG` に指定する。

## このディレクトリの中身

| ファイル | 置き先 | 備考 |
|---|---|---|
| `compose.yaml` | deploy-repo `stacks/<app>/compose.yaml` | 複製して使う |
| `build.toml` | deploy-repo `resources/builds.toml` へ追記 | `<app>` / `<repo>` を置換 |
| `stack.toml` | deploy-repo `resources/stacks.toml` へ追記 | `<app>` とポートを置換 |
| （`../../docker/nginx/default.conf.template`） | deploy-repo `stacks/<app>/docker/nginx/default.conf.template` | **ローカル開発と共有している原本**。複製する |

`compose.yaml` が読む変数はすべて `stack.toml` の `environment` から渡る。
アプリ側の設定キー（`JWT_SECRET_KEY` など）は `compose.yaml` が `APP_*` から詰め替える。
キーの一覧と意味は `.env.example` と `shared/kernel/settings/system_settings_defaults.py`。

## 手順

deploy-repo の `docs/new-stack.md` が正式なチェックリスト。ここはその上でこのテンプレート
固有の点だけを補う。

1. **名前を決める。** テンプレートの名前（`fastapitemplate`）のままにしない
   （[ADR-0023](../../docs/decisions/ADR-0023-komodo-build-and-deploy.md)）。
   イメージ名・スタック名・ネットワーク別名・データディレクトリがこの名前から派生する。
2. **ポートを採番表から計算する。** 空き番号を取らない（`stack.toml` のコメント参照）。
3. **`builds.toml` に Build を足す。**
   ⚠ **`pre_build` を必ず書く。** これが無いとイメージが版を名乗れない（下記）。
4. **`stacks/<app>/` に `compose.yaml` と `docker/nginx/default.conf.template` を複製する。**
5. **`stacks.toml` に Stack を足す。** `tags = ["managed"]` と
   `ignore_services = ["init-paths"]` を忘れない。
6. **秘密を Komodo の Variable に登録する。** `JWT_SECRET_KEY` は
   **必ず生成した値を入れる**（既定値のままだと誰でもトークンを偽造できる）。
7. push → ResourceSync → Build → DeployStack。
8. `curl http://10.10.2.11:<PORT>/healthz` で LAN 直叩き確認。
9. 公開するなら **Access を作ってから ingress** を足す（順序を逆にすると無認証で公開される）。

## ⚠ pre_build（版の刻印）

Komodo はコミット情報を build-arg で渡さず、`.dockerignore` が `.git` を除いているため
Dockerfile の中から git も引けない。**クローン済みのリポジトリで
`scripts/generate_version.sh` を走らせてからビルドに入る**必要がある。

```toml
[build.config.pre_build]
path = "."
command = "bash scripts/generate_version.sh"
```

書き忘れると、ビルドは成功するのに `/info`・システムステータス画面・起動ログが
`version=dev` のままになる。**動いているものが失敗し始めるのではなく、
「どのコミットが動いているか答えられない」状態が静かに続く**ので気付きにくい。

## ⚠ このイメージ側の約束（deploy-repo からは直せない部分）

- **upstream のホスト名を焼き込んでいない。** nginx 設定は bind mount で、
  引く先は `APP_WEB_ALIAS` で外から与える。
- **マイグレーションは entrypoint が流す**（`alembic upgrade head`）。初回起動は
  スキーマ構築を含むので healthcheck の `start_period` を 300s 取ってある。
- **実行ユーザーは UID 5678**（`Dockerfile` の `ARG APP_UID`）。`init-paths` が
  データディレクトリをこの UID に chown する。**片方だけ変えるとアプリが書けなくなる。**
- **0.0.0.0 で listen する**（gunicorn `--bind 0.0.0.0:8000`）。
- 永続データは `/app/data`（＝ `${APP_DATA_DIR}/data`）と DB のみ。

## 自動化されている範囲

| | |
|---|---|
| GitHub push → Komodo Build | webhook `/listener/github/build/<app>` を GitHub 側に足せば自動 |
| deploy-repo push → 定義同期 | `/listener/github/sync/deploy-repo/sync` |
| **本番スタックの入れ替え** | **手動**。push のたびに本番が入れ替わるのを避けるため意図的にそうしている |
