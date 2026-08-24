# ADR-0023: ビルドとデプロイを Komodo に一本化し、成果物はレジストリのイメージにする

- 日付: 2026-08-24
- 状態: 承認

## 文脈

このテンプレートのビルド・デプロイは「手元（またはデプロイ先の dev コンテナ）で
`scripts/build.sh` を実行して `dist/` にイメージの tar を書き出し、それを配置先へ転送して
`scripts/deploy.sh` を実行する」という、**レジストリを使わない持ち込み方式**だった。
デプロイの名前は配置場所から決め（ADR-0015）、コンテナ名の衝突は `deploy.sh` が自力で
片付け（ADR-0014）、公開ポートは `build-remote-container.env` から渡していた（ADR-0008）。
どれも「Synology の NAS に SSH で入って置く」ことを前提にした設計である。

前提が変わった。実行環境は Synology（naso）から nolumialab へ移り、そこには

- **コンテナレジストリ** `hub.nolumia.com:5000`（blob の実体は NAS の iSCSI LUN 上）
- **Komodo** — GitHub からクローンしてイメージを焼き、レジストリへ push する Build と、
  compose を配って起動する Stack を持つデプロイ基盤
- **deploy-repo** — 稼働状態の正となる Git リポジトリ。Komodo の ResourceSync がここを見る

が揃っている。このテンプレートから作られた `rewardpointsweb` は既にこの経路で動いており、
テンプレートだけが古い前提のまま取り残されていた。

そのうえ、Komodo でこのテンプレートのイメージを焼くと**バージョン情報が失われる**。
`Dockerfile` はビルド情報を `--build-arg`（`COMMIT_HASH` ほか）で受け取る作りだが、
Komodo はコミット情報を build-arg で渡さない。`.dockerignore` が `.git` を除いているため
Dockerfile の中から git を引くこともできない。結果、`/info`・システムステータス画面・
起動ログがそろって `version=dev` を答える。**ビルドは緑のまま**なので気付きにくい。

## 決定

1. **ビルドとデプロイは Komodo で行う。** 成果物は
   `hub.nolumia.com:5000/komodo/<app>` に push されるコンテナイメージ 1 つとする
   （タグは `latest` / `<コミット>` / `0.0.N`）。tar のバンドルは作らない。
2. **持ち込み方式を撤去する。** `scripts/build.sh` / `scripts/deploy.sh` /
   `scripts/build-remote-container.sh` と、それらを前提にした ADR-0008 / ADR-0014 /
   ADR-0015 を廃止する。GHCR へ push する `release.yml` も削除する。
3. **バージョン情報はビルドの前に生成してコンテキストへ入れる。**
   `scripts/generate_version.sh` を Komodo Build の `pre_build` で実行し、
   `shared/kernel/version.json` を作ってから `docker build` に入る。build-arg は使わない。
4. **デプロイ定義の雛形をテンプレートに同梱する**（`deploy/komodo/`）。
   compose・Build 定義・Stack 定義を、deploy-repo へ複製して使える形で置く。

## 理由

- **成果物を 1 つに絞れる。** 持ち込み方式では「`dist/` の中身」（image.tar 2 つ +
  deploy.sh + manifest）が成果物で、転送の破損検出も版の照合も自前で持つ必要があった
  （`manifest.sha256`）。レジストリはそれを標準で持っている。
  **保管先も実質変わらない**（レジストリの blob は NAS の iSCSI LUN 上にある）。
- **戻し方が単純になる。** Komodo がコミットごとにタグを打つので、
  スタックの `APP_IMAGE_TAG` をそのタグに変えれば戻る。`deploy.sh` の `reset` のように
  データを消す操作を巻き込まない。
- **`deploy.sh`（約 850 行）の保守が消える。** その大半は「配置場所から名前を決める」
  「コンテナ名を握った残骸を片付ける」「`.env` を壊さずに生成する」という、
  **compose プロジェクトを人手で並べるがゆえの問題**への対処だった。Komodo では
  スタック名が compose プロジェクト名になり、`.env` は Komodo が書き出し、
  ポートは採番表で決まる。問題そのものが無くなる。
- **バージョンは「ビルド前に生成」に一本化する。** build-arg 方式は渡す側（Makefile /
  GitHub Actions / Komodo）ごとに同じ値を並べ直す必要があり、現に `release.yml` は
  `Dockerfile` と違う名前（`APP_VERSION` / `GIT_SHA` / `BUILD_TIME`）を渡していて
  **噛み合っていなかった**。生成する場所を 1 つにすれば、渡し方の食い違いは起こらない。
  優先順位は **git > 既にある version.json > dev** とする。git が引ける場所（pre_build・
  手元）では必ず作り直し、引けない場所（イメージの中）では既にある内容を尊重する。
  Komodo はビルドディレクトリを使い回すため「既存を優先」にすると 2 回目以降が
  初回の版を名乗り続ける。逆にイメージ内で上書きにすると pre_build の結果が dev に潰れる。
- **デプロイ定義をテンプレートに置くのは、イメージ側の約束を一緒に配るため。**
  実行ユーザーの UID とデータディレクトリの所有者、`start_period` とマイグレーションの
  所要時間、nginx が引く upstream 名は、**イメージと compose の両方が合っていないと
  動かない**。deploy-repo 側にしか無いと、テンプレートから作った人がそれを知らずに
  自分で書くことになる。
- 採らなかった案:
  - **両方式を併存させる** — Komodo を正としつつ持ち込み方式も残す案。手順書が二重になり、
    どちらも中途半端に古びる。Komodo の無いホストへ置く要件は現時点で無い。
  - **build-arg を Komodo 側で埋める** — Komodo にコミット SHA を build-arg として
    渡す仕組みが無い。固定値しか書けないので用を成さない。
  - **`.git` をビルドコンテキストに入れて Dockerfile 内で git を引く** —
    `python:3.12-slim` に git を入れる必要があり、履歴の全部をコンテキストへ送ることになる。
  - **version.json をコミットする** — 生成側が既存を尊重するため、コミットされた内容が
    永久に優先され、どのイメージも同じ古い版を名乗る。`.gitignore` に入れて防いでいる。

## 影響

- **`dist/` を配置先へ転送する運用は無くなる。** 既にその形で動いている環境
  （naso 上の旧デプロイ）は、Komodo のスタックへ移すまで**このテンプレートの新しい版を
  受け取れない**。移行はアプリごとに deploy-repo へ Build / Stack を足して行う。
- **ADR-0008 / ADR-0014 / ADR-0015 は廃止**（この ADR で置き換え）。
  「テンプレートの名前のままにしない」という制約自体は残るが、強制する主体が
  `deploy.sh` の中断からスタック定義（イメージ名・スタック名・データディレクトリを
  人が書く）へ移る。**自動で止める仕組みは無くなる。**
- **公開ポートは採番表で決まる**（`10000 + プロジェクト×100 + 環境×10 + 種別`）。
  `WEB_HOST_PORT` はローカル開発だけの設定になった。
- **`db/Dockerfile` を廃止した。** 中身は素の MariaDB にタイムゾーン設定を足しただけで、
  同じ設定は compose 側で与えられる。ビルド 1 本ぶん依存が減る。
- **nginx 設定はローカル開発とデプロイで同じファイルを共有する**
  （`docker/nginx/default.conf.template`）。`upstream` ブロックをやめ、resolver + 変数
  経由の `proxy_pass` にした。upstream 名を起動時に 1 度だけ解決する形は、
  アプリを作り直した瞬間に 502 を返し続ける（実際に他プロジェクトの本番が落ちている）。
- **サービス名を `web` → `app`、`nginx` → `front` に変えた。** compose はサービス名を
  参加する全ネットワークの別名にする。デプロイ先の `edge` ネットワークはホスト全体で
  共有されるため、一般名を撒くと他スタックのコンテナを掴む／掴まれる。
- CI に `image.yml`（Dockerfile を触ったときだけ走る Docker ビルド）を足した。
  push はしない。版の刻印が効いているかもここで検証する。
