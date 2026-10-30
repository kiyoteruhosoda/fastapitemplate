# ADR-0086: CI は forge の自前の台で動き、GitHub から何も取らない

- 日付: 2026-10-30
- 状態: 承認
- 関連: ADR-0072 §5 を置き換える・task #171（GitHub から取らない）・task #172（像の uv を PyPI から）・task #603（Renovate の PR で docker の台を使わない）

## 文脈

ADR-0072 §5（旧 ADR-0030）は、CI が GitHub ホストのランナーで動き、GitHub の action を使う前提で書かれていた。
リポジトリを forge（`git.nolumia.com`。Forgejo）へ移してから、CI は `.forgejo/workflows/` の自前の台で動いている。
その時点で決めたこと（GitHub から何も取らない・uv と Python は forge の写しから取る・uv の版を書かない）は、
ワークフローの注釈と CLAUDE.md にしか無く、CLAUDE.md の中でも「`version` を固定する」と「版は書かない」が
食い違っていた。

## 決定

1. **CI は forge の Actions で、自前の台で動く。** 試験は `runs-on: [self-hosted, nolumialab]`、像のビルド
   （`image.yml`）は docker の入った台 `nolumialab-docker`。docker の台はジョブにホストの docker を渡すので、
   Renovate の PR では走らせない（task #603）。
2. **GitHub から何も取らない**（task #171）。
   - action は forge の鏡から取る（`actions/checkout@v6`・`actions/setup-node@v6`・`actions/upload-artifact@v3.2.2`）。
     鏡に無い `setup-uv` は自前の写しを完全な URL で指す（`https://git.nolumia.com/astral-sh/setup-uv@v10.0.1`）。
   - uv 本体は、forge の写しの一覧（`manifest-file: https://git.nolumia.com/astral-sh/uv/raw/branch/main/uv.ndjson`）から取る。
   - uv が入れる Python は `UV_PYTHON_INSTALL_MIRROR`（forge の `python-build-standalone` の写し）から取る。
   - Node は台の像（`node:24-bookworm`）のものを使う。`setup-node` に `node-version` を書かない
     （書くと鏡を指していても先に `api.github.com` の一覧を引く）。
3. **CI の uv は版を書かない。** `setup-uv` に `version` を書かず、写しの一覧の最新を使う。写しは
   `host/astral-mirror` が毎週取り込む。
4. **試験の Python は `.python-version` の版。** 本番の像（`Dockerfile` の `FROM python:…`）と揃っていることを
   CI の最初の段で確かめ、ずれたら落とす。
5. **本番の像の uv は PyPI から入れる**（`Dockerfile` の `ARG UV_VERSION`。task #172）。`ghcr.io/astral-sh/uv` の
   像から `COPY --from` しない。版は Renovate（`# renovate: datasource=pypi`）が上げ、CI の uv とは連動させない。
6. **action の版の固定**: 動く major タグがあるものはそれを使い、無いもの（`setup-uv`。上流が v8 以降
   major タグを出していない）だけ完全な版で固定する。`setup-uv` の行には、なぜそこだけ書き方が違うのかを
   注釈で残す。Node 20 を要求する版は使わない。

## 理由

- **GitHub の状態で CI が止まらないようにするため。** 無料枠・API の制限・障害のどれでも、取りに行く先が
  GitHub だと CI が赤くなる。forge に写しを置けば、外へ出るのは写しの取り込みだけになる。
- **uv の版を書かないのは、写しの取り込みが版上げの役を兼ねるため。** 版を書くと、写しに新しい版が入るたびに
  全アプリのワークフローを書き換えることになる。取り込みの後に全アプリが同時に赤くなり得るが、
  原因が 1 か所なので直しやすい。
- **本番の像の uv を CI と揃えないのは、像は Renovate の PR として人が見る段を通すため。** CI の uv は試験にしか
  使わず、像に残らない。
- **完全な版の固定を `setup-uv` だけに留めるのは、ADR-0072 §5 と同じ理由**（上流が major タグをやめたのは
  タグの差し替えによるサプライチェーン攻撃を避けるため。全部を完全な版にすると、派生アプリに月次の追随を押し付ける）。

## 影響

- ADR-0072 §5 はこの ADR で置き換える（docker の action 2 つ（`setup-buildx-action`・`build-push-action`）は、
  今のワークフローに無い）。
- 写しに無い Python の版へ上げると CI が落ちる。そのときは、その版のファイルを forge の
  `astral-sh/python-build-standalone` のリリースへ足す。
- 派生アプリは同じワークフローを持つ。写しの取り込みの後に赤くなったら、まず uv の新しい版を疑う。
