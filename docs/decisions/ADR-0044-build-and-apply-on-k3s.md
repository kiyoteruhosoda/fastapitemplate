# ADR-0044: デプロイ先は k3s にし、押す口は deck（build → pin → apply）にする

- 日付: 2026-09-21
- 状態: 承認
- 関連: ADR-0023（Komodo に一本化した。**この ADR で置き換える**）、
  ADR-0031（アプリ名の正本）、ADR-0034（画面の設定が環境変数より強い）、
  ADR-0035（新しい版は知らせるだけで当てない）

## 文脈

ADR-0023 は「成果物はレジストリのイメージ 1 つ」「配るのは Komodo」と決めた。
**前者は正しかったが、後者の前提が 2026-09-08 に消えた。**

- **Komodo（core / periphery / mongo）は停止した。** アプリは nolumialab の
  **k3s** の上にあり、稼働状態の宣言は deploy-repo の `k8s/<app>-<env>/` に置く。
  ⚠ **起こしてはならない** ——`DeployStack` を押すと compose 側が k3s と同じ
  データを掴みに行く。
- **ソースの正本は forge（`https://git.nolumia.com/kyon/<app>`）へ移った。**
  GitHub は押し出しミラーで、読み取り専用である。
- **Komodo の `Deploy` が「build する」「配る」「起動する」の 3 つを指していた**
  ことが、押す前に何が起きるか分からない原因だった。

このテンプレートの文書（README・CLAUDE.md・OPERATIONS.md・`deploy/komodo/`）は
どれも Komodo を前提に書かれていて、**ここから作ったアプリを載せる手順として
もう通らない**。

## 決定

1. **デプロイ先は k3s。** 稼働状態の正は deploy-repo の `k8s/<app>-<env>/` に置く
   宣言（namespace / PV・PVC / ConfigMap / SealedSecret / Deployment / Service）。
   compose はローカル開発だけのものになった。
2. **押す口は deck（`https://deck.nolumia.com`）。** 環境を選んで版を上げると、
   **build → pin → deploy** の 3 段が LAN の中で走る。
3. **成果物は今までどおりコンテナイメージ 1 つ。** 置き場は
   `hub.nolumia.com:5000/app/<image>`、タグは **`sha-<コミット>`**
   （⚠ `latest` も `0.0.N` も付けない）。
4. **宣言は digest で参照する。** 版を上げる＝`40-app.yaml` の
   `image: …@sha256:…` を書き換えること。これは pin の段が機械的に行う。
5. **秘密は封印して宣言に載せる**（Sealed Secrets）。⚠ 平文の `kind: Secret` を
   git に置かない。
6. **雛形はこのリポジトリが持つ**（`deploy/k8s/`）。ADR-0023 で決めた
   「デプロイ定義の雛形をテンプレートに同梱する」は形を変えて残す。

## 理由

- **押す前に何が起きるか分かる形にする。** build と apply を分け、deck の画面にも
  段として出す。⚠ **`apply` は収束しない・消さない** ——ずれても戻さず、git から
  消した資源も残る。これは「勝手に本番が変わらない」ことを取った結果である。
- **`:latest` では `kubectl apply` で版が上がらない。** 宣言が変わらないので
  rollout が起きず、レジストリに新しいものがあっても古い Pod のまま残る。しかも
  **どの版が動いているか宣言から読めず、戻せない**。digest なら履歴が git に残り、
  戻すのは前の digest に戻すだけで済む。
- **`0.0.N` を捨てたのは、版数が別のコミットを指し得るから。** Build を作り直すと
  0 に戻る。加えて週次の registry-prune は semver に触らないので永久に溜まる。
- **退避経路を 1 本残す。** deploy-repo の workflow 2 つ
  （`build-image.yml` / `apply-manifests.yml`。どちらも手押し）。
  ⚠ **これは「forge が落ちても」ではなく「deck が落ちても」上げられるようにする
  ためのもの**で、日常の入口ではない。
- 採らなかった案:
  - **Komodo を戻す** —— compose 側が k3s と同じデータを掴む。並走できない。
  - **マージで本番へ配る** —— push のたびに本番が入れ替わる。ADR-0035 で
    「新しい版は知らせるだけで当てない」と決めた向きと逆になる。
  - **宣言をアプリのリポジトリに置く** —— 稼働状態の正が散る。どのアプリが
    どの版で動いているかを 1 か所で読めなくなる。

## 影響

- **ADR-0023 は廃止**（この ADR で置き換え）。ただし次の 3 つは**引き継ぐ**。
  - 成果物はコンテナイメージ 1 つ
  - 版の刻印は**ビルドの前に** `scripts/generate_version.sh` で行う
    （`resources/build-matrix.json` の `pre_build: true` が build の段で走らせる）
  - サービス名に一般名を使わない（`app` / `front`）
- **`deploy/komodo/`（compose・`build.toml`・`stack.toml`）を消し、
  `deploy/k8s/` に置き換えた。** compose の雛形はデプロイ先には要らない
  ——nginx の設定は ConfigMap、データディレクトリは PV、秘密は SealedSecret になる。
- **`init-paths` は要らなくなった。** 所有者合わせは `fsGroup` が行う
  （使い捨てサービスが 1 つ消え、`ignore_services` の悩みも消えた）。
- **LAN へ出す番号は NodePort の既定の帯**を使う。採番との対応は
  **`30000 +（採番の番号 - 10000）`**。⚠ compose は 10000 番台なので、
  **docker と番号が構造的に重ならない**。
- **`replicas` を宣言に書かない。** 台数の正本は deck の scale だけで、書くと
  `apply` が止めてある環境を起こす。
- ⚠ **`docker/nginx/default.conf.template` は共有ではなくなった。** デプロイ先の
  nginx 設定は deploy-repo の `20-config.yaml`（ConfigMap）にあり、**resolver が
  違う**（docker の `127.0.0.11` ではなく CoreDNS の `10.43.0.10`）。片方を直したら
  もう片方も直す。
- ⚠ **成功表示は証拠にならない。** build も apply も、何も入らないまま success で
  返ることがある。**`/info` の commit と、動いている Pod の `imageID`** で確かめる。
