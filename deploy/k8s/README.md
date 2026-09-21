# k3s へのデプロイ

このテンプレートから作ったアプリを nolumialab の **k3s** で動かすための宣言の雛形。
方式そのものは [ADR-0044](../../docs/decisions/ADR-0044-build-and-apply-on-k3s.md)。

```
forge のソース ──▶ build ──▶ hub.nolumia.com:5000/app/<image>:sha-<コミット>
（git.nolumia.com）              ＝ 成果物（コンテナイメージ 1 つ）
                                          │ digest
                                          ▼
     deploy-repo の k8s/<app>-<env>/ ──apply──▶ k3s（nolumialab）
     ＝ 稼働状態の正（宣言）
```

**押す口は deck（https://deck.nolumia.com）。** 環境を選んで版を上げると、
**build → pin → deploy** の 3 段が LAN の中で走る。

| 段 | 何をするか |
|---|---|
| **build** | イメージを焼いて registry へ push する（タグは `sha-<コミット>`）|
| **pin** | その digest を `k8s/<app>-<env>/40-app.yaml` に書き戻して main へ commit する |
| **deploy** | `k8s/<app>-<env>/` をクラスタへ `apply` する |

⚠ **Komodo は 2026-09-08 に停止した。起こさないこと**（compose 側が k3s と同じ
データを掴みに行く）。

⚠ **退避経路は deploy-repo の workflow 2 つ**（`build-image.yml` /
`apply-manifests.yml`。どちらも手押し）。**deck が落ちている日のためのもの**で、
日常の入口ではない。⚠ どちらも既定が安全側（apply は `plan`、build の pin は
`*-stg`）なので、**prod へ入れるには 2 つとも明示が要る** ——明示しないと
**何も入らないまま success が返る**。

## このディレクトリの中身

deploy-repo の `k8s/<app>-<env>/` へ複製し、`<app>` / `<env>` / `<host>` / 番号 /
digest を置き換える。**実物の見本は deploy-repo の `k8s/fastapitemplate-stg/`。**

| ファイル | 中身 |
|---|---|
| `00-namespace.yaml` | namespace と、deck が環境を並べるためのラベル |
| `10-storage.yaml` | PV 2 つ（DB / アプリのデータ）と PVC 2 つ |
| `20-config.yaml` | ConfigMap。アプリの設定と nginx の設定 |
| （`25-secrets.yaml`）| **封印した秘密。ここには置けない**（下記の手順で作る）|
| `30-db.yaml` | MariaDB |
| `40-app.yaml` | app（FastAPI）と front（nginx）＋ LAN へ出す NodePort |

⚠ **`apply` する単位はディレクトリ**（`.yaml` を全部。`.sh` と `.md` は無視。
再帰はしない）。ファイル名の番号がそのまま当たる順序になる。

## 手順

```
[ ] 1. 名前を決める（テンプレート名のままにしない）
[ ] 2. 番号を採番表から計算する（NodePort = 30000 +（採番の番号 - 10000））
[ ] 3. build の表にこのアプリを足す
[ ] 4. 宣言を deploy-repo の k8s/<app>-<env>/ へ置く
[ ] 5. 置き場のディレクトリと持ち主を作る
[ ] 6. 秘密を封印して 25-secrets.yaml にする
[ ] 7. 一度 build → pin → apply を通す
[ ] 8. LAN 直叩きで疎通確認
[ ] 9. 公開するなら Access を作ってから ingress（逆順は無認証で公開される）
[ ] 10. deck の画面に環境が出ることを確かめる
```

### 1. 名前

テンプレートの名前（`fastapitemplate`）のままにしない。namespace・イメージ名・
置き場のディレクトリがこの名前から派生する。**アプリ自身の名前の正本は
`pyproject.toml` の `[project].name`**（[ADR-0031](../../docs/decisions/ADR-0031-the-app-name-comes-from-pyproject.md)）。

### 2. 番号

**採番の正本は Wiki の「ポート採番」。空き番号を勝手に取らない。**

```
採番       = 10000 + プロジェクト×100 + 環境×10 + 種別×1
NodePort  = 30000 +（採番の番号 - 10000）
```

⚠ **継続して動かすものを「その他」（9）に置かない。** 10900 番台の中で先着と
衝突する。このテンプレート自身が 2026-08-24 にこれを踏んで、専用の番号 5
（10500 / 10510 → **30500 / 30510**）へ移している。

### 3. build の表

build が引く表は deploy-repo の `resources/build-matrix.json`。⚠ **これを手で
書かない** ——いまの正本は `resources/builds.toml`（Komodo 時代の名残）で、JSON は
`python3 bin/check-build-matrix.py --write` で起こす。CI が両者のずれを落とす。

正本のほうに 1 件足す。

```toml
[[build]]
name = "<app>"
[build.config]
repo = "kiyoteruhosoda/<repo>"
branch = "main"
build_path = "."
dockerfile_path = "Dockerfile"
image_name = "<app>"

# ⚠ **これが無いと `/info` が版を答えられない。**
[build.config.pre_build]
path = "."
command = "bash scripts/generate_version.sh"
```

⚠ **`pre_build` を必ず書く。** これが**版の刻印**で、無いとイメージが
`version=dev` を名乗り続ける（[scripts/README.md](../../scripts/README.md)）。
**ビルドは緑のままなので気付けない。**

⚠ **`repo` は GitHub の綴りのままでよい。** build は**まず forge
（`kyon/<名前>`）を見て、無ければ GitHub（押し出しミラー）へ落ちる**ので、
移送が済んでいれば勝手に forge 側から取る。

⚠ **push 先はこの表では決まらない。** build は常に
`hub.nolumia.com:5000/app/<image>` へ押す（`komodo_namespace` は Komodo 時代の
名残で、いまは使われていない）。

### 4〜5. 宣言と置き場

このディレクトリを複製して置き換える。置き場のディレクトリと持ち主は
**人が先に作る**（`10-storage.yaml` のコメント）。

### 6. 秘密

**封印して宣言に載せる**（平文の `kind: Secret` を git に置くと CI が落ちる）。
このテンプレートが要求するのは次の 2 つ。

| Secret | 鍵 |
|---|---|
| `<app>-db` | `MARIADB_ROOT_PASSWORD` / `MARIADB_USER` / `MARIADB_PASSWORD` / `MARIADB_DATABASE` |
| `<app>-app` | `DATABASE_URI` / `JWT_SECRET_KEY` / `SECRET_KEY` / `ADMIN_INITIAL_PASSWORD` |

⚠ **`JWT_SECRET_KEY` は必ず生成した値を入れる。** 既定値のままだと誰でも
トークンを偽造できる（`docs/Progress.md` の T2）。

```bash
# 1. 値を入れる（kubectl create secret を手で）
# 2. 封印して宣言にする
ssh nolumialab 'bash -s' -- <app>-<env> \
  < k8s/sealed-secrets/seal.sh > k8s/<app>-<env>/25-secrets.yaml
# 3. 手で作った Secret を controller に引き取らせる
ssh nolumialab 'bash -s' -- <app>-<env> < k8s/sealed-secrets/adopt.sh
```

⚠ **値を 1 つ差し替えるときに全部を封印し直さない**（封印は毎回あたらしい
セッション鍵を使うので、関係の無い値まで差分になる）。`kubeseal --raw` で 1 つだけ
差し替える。手順は deploy-repo の `k8s/sealed-secrets/README.md`。

### 7〜8. 通して確かめる

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://10.10.2.11:<NodePort>/healthz
curl -s http://10.10.2.11:<NodePort>/info        # version / commit / branch
```

⚠ **成功表示を証拠にしない。** 押した digest と、実際に動いている Pod の
`imageID` を突き合わせる。

```bash
ssh nolumialab "sudo k3s kubectl -n <app>-<env> get po -o jsonpath=\
'{.items[*].status.containerStatuses[*].imageID}'"
```

## ⚠ このイメージ側の約束（宣言からは直せない部分）

- **マイグレーションは entrypoint が流す**（`alembic upgrade head`）。デプロイの
  手順としては分かれていない。⚠ 初回は空の DB からスキーマを作るので、
  `livenessProbe` の `initialDelaySeconds` を長く取ってある（短いと途中で殺される）。
- **実行ユーザーは UID 5678**（`Dockerfile` の `ARG APP_UID`）。置き場の所有者
  （`10-storage.yaml` の chown）と `fsGroup` を揃える。**片方だけ変えると書けない。**
- **`0.0.0.0:8000` で listen する**（gunicorn）。
- **永続データは `/app/data` と DB だけ。**
- **upstream のホスト名を焼き込んでいない。** 引く先は nginx の ConfigMap 側で決まる。

## 止める・起こす

**deck の画面から**（書き込みは `replicas` の scale 1 点だけ）。
⚠ **stg は普段 `replicas=0` で止めてある。** だから宣言に `replicas` を書かない
——書くと `apply` が止めてある環境を起こす。
