# ADR-0031: アプリ自身の名前は `pyproject.toml` から導く

- 日付: 2026-09-05
- 状態: 承認

## 文脈

このテンプレートは「起こしたら名前を変える」ことを前提にしている（ADR-0023。名前から
イメージ名・スタック名・ネットワーク別名・データディレクトリが導かれる）。ところが
**アプリの名前がコードに直に書かれている箇所が 2 つ**あった。

| 場所 | 書いてあった値 |
|---|---|
| `presentation/fastapi/app.py` の `FastAPI(title=...)` | `"fastapitemplate"` |
| `identity_federation/.../oidc_metadata.py` の `USER_AGENT` | **`"nolumiawiki"`** |

後者は、派生アプリ（nolumiawiki）で入れた修正をテンプレートへ戻すときに値ごと持ち帰った
もので、**以後この行を直さないかぎり、あらゆる派生アプリが IdP に対して
「nolumiawiki」と名乗り続ける**状態になっていた。2026-09-05 に `mp3play` を起こした
ときに気付いた。どちらも動きはするので、**誰も困らないまま間違い続ける**類の欠陥である。

## 決定

**名前の正本を `pyproject.toml` の `[project].name` 1 か所にする。**
`shared/kernel/version.py` に `project_name()` を置き、`BuildInfo.name` として運ぶ。
Swagger の題と、外向きの `User-Agent` はここから導く。

## 理由

- **テンプレートの約束と噛み合う。** 「起こしたら名前を変える」の「名前」は
  `pyproject.toml` の `name` を含む。そこを変えれば全部追随するなら、**覚えることが
  1 つ減る**。設定キーを新設すると「変えるべき場所」が増えて、同じ間違いが再発する。
- **デプロイの変数にしない。** `APP_DISPLAY_NAME`（画面に出る名前）や
  `ACCESS_TOKEN_ISSUER`（スタック名）は環境ごとに変わりうるが、**ソフトウェアの名前は
  版と一緒に動く**。イメージの中で完結させるほうが素性に合う。
- `pyproject.toml` はイメージに入っている（`Dockerfile` が `COPY` している）。
  読めなかったときは `"app"` に落とす——**テンプレート名を既定にしない**のは、
  読めていないことに気付けなくなるため。

## 影響

- `BuildInfo` に `name` が増える。構築しているのは `load_build_info()` だけなので、
  読み手（`/info`・システムステータス画面）は影響を受けない。
- `USER_AGENT` は `"<name>/<version>"` の形になる。IdP の前段（Cloudflare 等）が
  UA で弾く問題は、名前が付いてさえいれば起きない。
- `tests/unit/test_version.py` が「直書きに戻っていないこと」を見張る。
- **派生アプリ側の直書きは自動では消えない。** `git merge template/main` を取り込んだら、
  `app.py` と `oidc_metadata.py` に自分で書いた名前が残っていないか確かめること。
