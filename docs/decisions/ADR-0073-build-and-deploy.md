# ADR-0073: ビルド・配布と本番の守り

- 日付: 2026-10-30
- 状態: 承認
- 統合した ADR: 旧 ADR-0044（§1）・旧 ADR-0031（§2）・旧 ADR-0032（§3）・旧 ADR-0056（§4）・旧 ADR-0059（§5）（2026-10-30 に統合。元の文面は git の履歴にある）

## 文脈

このテンプレートから起こしたアプリは、nolumialab の **k3s** の上で動く。ソースの正本は forge
（`https://git.nolumia.com/kyon/<app>`）で、GitHub は押し出しの読み取り専用ミラーである。
稼働状態の宣言は deploy-repo の `k8s/<app>-<env>/` に置き、版を上げる口は deck
（`https://deck.nolumia.com`）である。前の配り方（イメージの tar を NAS へ持ち込む `deploy.sh`、
その後の Komodo）は畳んだ。

この ADR は「イメージをどう焼いて配るか」と、「配ったものが本番で、雛形の既定のままでも安全に
振る舞うか」（名前・受け皿・既定値・守りのヘッダ）をまとめて扱う。どれも**雛形から起こすたびに
書き換え忘れ・写し忘れが起こりうる**という同じ弱点への手当てである。

## 決定

### §1 デプロイ先は k3s、押す口は deck（build → pin → apply）

Komodo の `Deploy` が「build する」「配る」「起動する」の 3 つを指していて、押す前に何が起きるか
分からなかった。段を分けて見える形にする。

1. **デプロイ先は k3s。** 稼働状態の正は deploy-repo の `k8s/<app>-<env>/` に置く宣言
   （namespace / PV・PVC / ConfigMap / SealedSecret / Deployment / Service）。
   compose はローカル開発だけのものである。
2. **押す口は deck。** 環境を選んで版を上げると、**build → pin → deploy** の 3 段が LAN の中で走る。
   main へのマージでも、deploy-repo の `resources/projects.json` に載ったプロジェクトの prod は
   deck が同じ 3 段を自動で走らせる（deck の ADR-0119）。手で押すのは deck の画面から。
3. **成果物はコンテナイメージ 1 つ。** 置き場は `hub.nolumia.com:5000/app/<image>`、タグは
   **`sha-<コミット>`**（⚠ `latest` も `0.0.N` も付けない）。
4. **宣言は digest で参照する。** 版を上げる＝`40-app.yaml` の `image: …@sha256:…` を書き換えること。
   これは pin の段が機械的に行う。
5. **秘密は封印して宣言に載せる**（Sealed Secrets）。⚠ 平文の `kind: Secret` を git に置かない。
6. **宣言の雛形はこのリポジトリが持つ**（`deploy/k8s/`）。イメージ側の約束（実行ユーザーの UID と
   データディレクトリの所有者、起動の猶予とマイグレーションの所要時間、nginx が引く上流の名前）は
   イメージと宣言の両方が合っていないと動かないので、一緒に配る。
7. **版の刻印はビルドの前に行う。** `scripts/generate_version.sh` が `shared/kernel/version.json` を作り
   （`resources/build-matrix.json` の `pre_build: true` で build の段が走らせる）、それから
   `docker build` に入る。build-arg は使わない。優先順位は **git > 既にある version.json > dev**。
   ⚠ `version.json` はコミットしない（`.gitignore` に入れてある）。
8. **サービス名に一般名を使わない**（`web` ではなく `app`、`nginx` ではなく `front`）。

### §2 アプリ自身の名前は `pyproject.toml` から導く

名前がコードに直書きされていて、派生アプリから持ち帰った `USER_AGENT = "nolumiawiki"` のせいで、
あらゆる派生アプリが IdP に「nolumiawiki」と名乗っていた（2026-09-05、`mp3play` を起こして気付いた）。

1. **名前の正本は `pyproject.toml` の `[project].name` 1 か所。** `shared/kernel/version.py` の
   `project_name()` が読み、`BuildInfo.name` として運ぶ。
2. Swagger の題（`presentation/fastapi/app.py` の `FastAPI(title=...)`）と、外向きの `User-Agent`
   （`identity_federation/.../oidc_metadata.py`。形は `"<name>/<version>"`）はここから導く。
3. 読めなかったときは `"app"` に落とす。テンプレート名を既定にしない。

### §3 SPA の受け皿は `/api/` を飲み込まない

`presentation/fastapi/routers/spa.py` は React Router の履歴モードのために `GET /{path:path}` を
受け、実在しないパスへ `index.html` を返す。このルーターは `frontend/dist` があるとき（＝本番）だけ
載るので、存在しない API が**本番でだけ** `200` + HTML を返していた。

1. **受け皿に落ちた `/api/` 配下は 404 を返す。** 応答の形は `dist` の無いときと同じ（FastAPI 既定の 404）。
2. 実在する成果物が `dist/api/…` に在れば、そちらが優先する。
3. `/docs`・`/metrics` のような API 以外の経路は受け皿へ落ちてよい（実在するルーターが先に応えるので、
   落ちるのは打ち間違えたときだけ）。

### §4 本番では、公開されている既定値（署名鍵・管理者のパスワード）で動かない

雛形にはリポジトリに載った（誰でも読める）既定値が 2 つある。署名鍵 `JWT_SECRET_KEY` の既定値
（アクセストークンの検証は DB を引かない（ADR-0076 §5）ので、この鍵で作ったトークンは書いた権限の
まま通る）と、既定の管理者（`admin@example.com`・全権の `owner`）のパスワードである
（2026-10-21 の脆弱性確認、task #573）。

`APP_ENV=production` のときだけ、次の 2 つを断る。

1. 署名鍵が空・既定値・32 文字未満なら、**アプリを組み立てない（起動しない）**
   （`shared/kernel/settings/secret_guard.py`）。
2. パスワードのログインで、**公開されている既定のパスワードでは入れない**（401。理由は他の失敗と
   同じ `invalid_credentials`。監査ログの `reason` は `default_password`）。既定の管理者に限らず、
   その値で入ろうとしたら誰でも断る。

それ以外の環境（開発・stg）は、1 は警告だけ、2 は入れる。

### §5 守りのヘッダはアプリ自身が付ける

画面と API の応答に守りのヘッダが 1 つも付いておらず、クリックジャッキング（他のサイトが画面を
透明な枠で重ねて押させる攻撃）を防げなかった（2026-10-21 の脆弱性確認、task #576）。

`presentation/fastapi/middleware/security_headers.py` の `SecurityHeadersMiddleware` が、全部の応答に
付ける。いちばん外側に置き、CSRF で断った応答にも付ける。

1. `Content-Security-Policy: default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`
2. `X-Frame-Options: DENY`・`X-Content-Type-Options: nosniff`・`Referrer-Policy: no-referrer`
3. `Strict-Transport-Security: max-age=31536000` は `SESSION_COOKIE_SECURE` が有効なとき（https で配るとき）だけ
4. `/docs`・`/redoc` は外の CDN からスクリプトを読むので、CSP だけ付けない
5. 個別の応答が自分で付けたヘッダは上書きしない

## 理由

### §1

- **押す前に何が起きるか分かる形にする。** build と apply を分け、deck の画面にも段として出す。
  ⚠ **`apply` は収束しない・消さない** ——ずれても戻さず、git から消した資源も残る。
  「勝手に本番が変わらない」ことを取った結果である。
- **`:latest` では `kubectl apply` で版が上がらない。** 宣言が変わらないので rollout が起きず、
  どの版が動いているかも宣言から読めず戻せない。digest なら履歴が git に残り、戻すのは前の digest に
  戻すだけで済む。`0.0.N` は作り直すと 0 に戻って別のコミットを指し得るうえ、週次の registry-prune が
  semver に触らないので永久に溜まる。
- **版の刻印を 1 か所にする。** build-arg は渡す側ごとに同じ値を並べ直す必要があり、実際に名前が
  食い違っていた。git が引ける場所（pre_build・手元）では必ず作り直し、引けない場所（イメージの中。
  `.dockerignore` が `.git` を除く）では既にある内容を尊重する。ビルドディレクトリが使い回されても
  前の版を名乗らず、イメージ内で dev に潰れもしない。
- **一般名のサービス名は、共有のネットワークで他のスタックのコンテナを掴む／掴まれる**
  （compose はサービス名を参加する全ネットワークの別名にする）。
- **退避経路を 1 本残す。** deploy-repo の workflow 2 つ（`build-image.yml` / `apply-manifests.yml`。
  どちらも手押し）。⚠ **これは「forge が落ちても」ではなく「deck が落ちても」上げられるようにする
  ためのもの**で、日常の入口ではない。
- 採らなかった案:
  - **Komodo を戻す** —— compose 側が k3s と同じデータを掴む。並走できない。
  - **宣言をアプリのリポジトリに置く** —— 稼働状態の正が散り、どのアプリがどの版で動いているかを
    1 か所で読めなくなる。
  - **`.git` をビルドの文脈に入れて Dockerfile の中で git を引く** —— 土台の像に git が要り、履歴を
    全部送ることになる。

### §2

- **テンプレートの約束と噛み合う。** 「起こしたら名前を変える」の「名前」は `pyproject.toml` の
  `name` を含む。そこを変えれば全部追随するなら覚えることが 1 つ減る。設定キーを新設すると
  変えるべき場所が増えて、同じ間違いが再発する。
- **デプロイの変数にしない。** `APP_DISPLAY_NAME`（画面に出る名前）や `ACCESS_TOKEN_ISSUER` は環境ごとに
  変わりうるが、ソフトウェアの名前は版と一緒に動く。`pyproject.toml` はイメージに入っている
  （`Dockerfile` が `COPY` している）ので、イメージの中で完結する。
- 読めなかったときにテンプレート名へ落とさないのは、読めていないことに気付けなくなるため。

### §3

- **呼んだ側は JSON を待っている。** HTML の 200 を返すと、クライアントは成功と読んでからパースに
  失敗する。失敗の理由が 2 段ずれる。
- **同じアプリが環境で違う答えを返すのをやめる。** 「手元と CI では 404、本番では 200」は再現しない
  不具合の温床になる。打ち間違えた API が `no-cache` の `index.html` を毎回落とすのは帯域の無駄でもある。

### §4

- 警告はログにしか出ず、本番のログを毎日読む人はいない。気付かせる確実な方法は動かないこと。
- 鍵は「既定値でない」だけでは足りないので長さも見る（`openssl rand -base64 48` で 64 文字）。
- 管理者を「起動しない」で塞ぐと、`ADMIN_INITIAL_PASSWORD` を渡したかを起動時に知る方法が無い
  （投入は利用者が居ないときにしか値を使わない。ADR-0078 §3）。ログインの時点で値そのものを見れば、
  渡し忘れた環境でも、後から既定値に戻した環境でも同じように塞げる。
- 採らなかった案: 既定の管理者をパスワード無しで作る。開発の据え付け直後に入れなくなり、README の
  手順（既定のパスワードで入って変える）が崩れる。

### §5

- アプリ自身が付ければ、雛形から起こしたアプリには写し忘れなく入る。前段の nginx の設定はアプリごとに
  deploy-repo の `k8s/<app>-<env>/20-config.yaml` へ写すもので、実際に試し場の写しは雛形の `/metrics` の
  閉じ方すら写していなかった。
- 画面はインラインのスクリプトも外部の資源も使っていないので `'self'` で縛れる。例外は二要素の
  QR コード（`data:` の画像）だけ。
- `Referrer-Policy: no-referrer` は、再設定のリンク（`?token=`）を開いた画面から URL を外へ漏らさないため。
- 採らなかった案: Cloudflare の設定で付ける。アプリの外の設定で、派生のアプリへ写らない。

## 影響

### §1

- `deploy/k8s/` が宣言の雛形である。compose の雛形はデプロイ先には要らない ——nginx の設定は
  ConfigMap、データディレクトリは PV、秘密は SealedSecret になる。データディレクトリの所有者合わせは
  `fsGroup` が行う（使い捨ての `init-paths` サービスは要らない）。
- **LAN へ出す番号は NodePort の帯**を使う。採番との対応は **`30000 +（採番の番号 - 10000）`**。
  ⚠ compose は 10000 番台なので、docker と番号が構造的に重ならない。
- **`replicas` を宣言に書かない。** 台数の正本は deck の scale だけで、書くと `apply` が止めてある環境を起こす。
- ⚠ **`docker/nginx/default.conf.template` はデプロイ先と共有していない。** デプロイ先の nginx 設定は
  deploy-repo の `20-config.yaml`（ConfigMap）にあり、**resolver が違う**（docker の `127.0.0.11` ではなく
  CoreDNS の `10.43.0.10`）。片方を直したらもう片方も直す。どちらも `upstream` ブロックではなく
  resolver ＋変数経由の `proxy_pass` にする（上流の名前を起動時に 1 度だけ引く形は、アプリを
  作り直した瞬間から 502 を返し続ける）。
- ⚠ **成功表示は証拠にならない。** build も apply も、何も入らないまま success で返ることがある。
  **`/info` の commit と、動いている Pod の `imageID`** で確かめる。
- CI の `image.yml` は Dockerfile を触ったときだけ Docker ビルドを走らせ、版の刻印が効いているかを
  確かめる。push はしない。

### §2

- `tests/unit/test_version.py` が直書きに戻っていないことを見張る。
- **派生アプリ側の直書きは自動では消えない。** `git merge template/main` を取り込んだら、`app.py` と
  `oidc_metadata.py` に自分で書いた名前が残っていないか確かめる。

### §3

- `tests/integration/api/test_spa.py` が、**dist を作った状態で**本物のアプリへ `/api/nonexistent` を
  投げて 404 を確かめる。Backend の CI はフロントエンドを焼かないので、受け皿の取りこぼしはこの形でしか出ない。

### §4

- 本番で既定のパスワードのまま据わった管理者は入れない。付け直しは `docs/OPERATIONS.md` の
  「管理者がパスワードを忘れてサインインできないとき」と同じ手順で行う。
- 派生のアプリが `APP_ENV` を `production` 以外の名前で本番に出すと、この守りは効かない。
  宣言の雛形（`deploy/k8s/20-config.yaml`）は `production` にしてある。

### §5

- 画面に外の資源（CDN のフォント・解析のスクリプトなど）を足すときは CSP を広げる。広げずに足すと
  読み込みが断られる（実ブラウザの見張り（ADR-0072 §6）が CSP の違反で落とす）。
- `/docs`・`/openapi.json` は外から見える（API の仕様は Swagger が唯一の出所という決めごとのため、
  閉じるかは別に決める）。
