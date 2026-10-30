# TEMPLATE — このテンプレートの使い方

このリポジトリは、FastAPI＋React のアプリを始めるための**雛形**です。ここから新しいアプリ（派生アプリ）を作り、
要らない見本を消し、自分の機能を足していきます。この文書はその手順をまとめたマニュアルです。

- 個々の操作のコマンドは [OPERATIONS.md](OPERATIONS.md)、設計の解説は [ARCHITECTURE.md](ARCHITECTURE.md)、
  決めたことの理由は [decisions/](decisions/README.md)（ADR）にあります。ここからはリンクで辿ります。
- 守るべき規則（層・権限・時刻・ログ・品質ゲート）は [CLAUDE.md](../CLAUDE.md) が正本です。

---

## 1. 入っているもの

| 区分 | 中身 | 場所 | 決定 |
|---|---|---|---|
| 認証 | パスワード・二要素認証（TOTP）・パスキー・パスワードリセット・ログイン試行の制限 | `presentation/fastapi/`・`bounded_contexts/account_security/` | ADR-0076 |
| SSO | 外部 IdP（OIDC）でのサインイン・停止の受け取り・定期照合 | `bounded_contexts/identity_federation/` | ADR-0077 |
| 認可 | scope（権限コード）・ロール・アクティブロールの切り替え・権限を動かす関門 | `shared/domain/auth/master_data.py` | ADR-0078・ADR-0084 |
| テナント | 組織ごとの区切り・テナントの外の運用者とサポート担当 | `shared/infrastructure/` | ADR-0079 |
| 設定 | システム設定（全体。DB > 環境変数 > 既定値）とコンテンツ設定（テナントごと） | `shared/kernel/settings/`・`bounded_contexts/content_settings/` | ADR-0074・ADR-0085 |
| 記録 | アプリログと監査ログ（画面から検索）・保持期間の掃除 | `shared/kernel/logging/`・`bounded_contexts/audit/` | ADR-0075 |
| 通知 | お知らせ（ベル・Web Push・FCM）・メール送信 | `bounded_contexts/notification/`・`bounded_contexts/email_sender/` | ADR-0081 |
| スマホ | Android アプリからの呼び出し（口の例は `routers/app_session.py`）・最新版の案内 | `bounded_contexts/app_release/` | ADR-0081 |
| 機械の口 | 他のアプリ・バッチから呼ばれる口を足すときの基準と、外せない検証（方針） | — | ADR-0082 |
| 画面 | 管理画面 SPA（日英・テーマ・PWA・メンテナンス画面） | `frontend/` | ADR-0080 |
| 運用 | `/healthz`・`/readyz`・`/info`・`/metrics`・自己再起動 | `presentation/fastapi/routers/health.py` | ADR-0074 §2 |
| 配布 | コンテナイメージ 1 つ・k3s の宣言の雛形 | `Dockerfile`・`deploy/k8s/` | ADR-0073 |
| 品質 | 8 つの必須ゲート・設計の定量基準・E2E の煙試験 | `Makefile`・`.forgejo/workflows/` | ADR-0072 |

### 見本（自分の機能ができたら消すもの）

| 見本 | 何の見本か | 場所 |
|---|---|---|
| アイテム（`items`） | いちばん小さな機能の作り（4 層・テナントで絞るリポジトリ・画面） | `bounded_contexts/example/`・`frontend/src/pages/ItemsPage.tsx` |
| 共有メモ（`notes`） | 持ち主・共有で 1 件ずつ可否が変わる機能（ADR-0078 §6） | `bounded_contexts/notes/`・`frontend/src/pages/NotesPage.tsx` |
| コンテンツ設定の項目 `item_list_order` | テナントごとの設定を読む側の作り（ADR-0085） | `bounded_contexts/content_settings/domain/definitions.py` |

---

## 2. 新しいアプリを始める

### 2.1 リポジトリを作る

- **deck から作る（推奨）**: deck の「プロジェクトを作る」（`https://deck.nolumia.com/projects/new`）で
  fastapitemplate 型を選ぶ。リポジトリ・deploy-repo の宣言・秘密・IdP の登録までまとめて作られる。
- **手で作る**: forge に空のリポジトリを作り、このリポジトリの `main` を押し込む。デプロイの宣言は
  [deploy/k8s/README.md](../deploy/k8s/README.md) の手順 1〜10 で作る。

どちらの場合も、後で雛形の更新を取り込めるように、このリポジトリを `template` という名前の remote に足しておく
（5 章）。

### 2.2 名前を付け替える

⚠ **`fastapitemplate` のまま動かさない。** namespace・イメージ名・置き場がこの名前から決まり、名乗ったままだと
雛形由来のほかのアプリとそれらを取り合う（ADR-0073 §1）。名前を間違えても自動では止まらない。

| ファイル | 変えるところ |
|---|---|
| `pyproject.toml` | `[project].name`（**アプリ自身の名前の正本**。Swagger の題と外向きの `User-Agent` がここから決まる。ADR-0073 §2） |
| `shared/kernel/settings/system_settings_defaults.py` | `ACCESS_TOKEN_ISSUER`・`ACCESS_TOKEN_AUDIENCE`・`TOTP_ISSUER`・`WEBAUTHN_RP_NAME` |
| `tests/unit/test_settings.py` | 上の既定値を確かめている行 |
| `frontend/package.json` | `name` |
| `frontend/index.html` | `<title>` |
| `frontend/vite.config.ts` | PWA の `name`・`short_name` |
| `frontend/src/i18n/ja.json`・`en.json` | `app.title` |
| `Makefile` | `IMAGE` |
| `docker-compose.yml`・`.env.example` | `WEB_IMAGE`・`APP_WEB_ALIAS`・`DOCKER_NETWORK_NAME`・`WEBAUTHN_RP_NAME` の既定値 |
| `README.md` | 題と説明（2.4） |

付け替えたら、名前が残っていないかを確かめる。

```bash
git grep -n -i fastapitemplate -- ':!docs/CHANGELOG.md' ':!docs/decisions' ':!uv.lock' ':!frontend/package-lock.json'
```

アイコンを変えるときは [OPERATIONS.md「アプリのアイコン（PWA・favicon）を変えたいとき」](OPERATIONS.md)。

### 2.3 最初に動かす

1. 手元で動かす: [OPERATIONS.md「ローカル開発を始めたいとき」](OPERATIONS.md)。
   初期管理者は `admin@example.com` / `admin@example.com`。
2. 本番へ配ったら、⚠ **その日のうちに**次の 3 つを済ませる。
   - 署名鍵 `JWT_SECRET_KEY` を生成して秘密に入れる（既定値のままだと本番は起動しない。ADR-0073 §4）
   - 運用者（`system-admin`）を作る: [OPERATIONS.md「システム管理者を作りたいとき」](OPERATIONS.md)
   - 既定の管理者 `admin@example.com` のパスワードを変えるか、使わないなら消す（本番では既定のパスワードでは入れない）
3. SSO を使うなら: [OPERATIONS.md「SSO（外部 IdP との連携）を有効にしたいとき」](OPERATIONS.md)。

### 2.4 文書を自分のものにする

| 文書 | 派生アプリでの扱い |
|---|---|
| `README.md` | 自分のアプリの説明に書き直す。この雛形の機能一覧は要らない |
| `docs/TEMPLATE.md`（この文書） | 残す。雛形の更新を取り込むときと、見本の作りを見返すときに使う |
| `docs/CHANGELOG.md` | 雛形の履歴を消し、自分の履歴を書き始める（雛形の履歴は `template` の remote で読める） |
| `docs/decisions/` | **雛形の ADR は消さない**（受け継いだ設計の理由）。自分の ADR は続きの番号で足す |
| `CLAUDE.md`・`docs/ARCHITECTURE.md`・`docs/ER.md`・`docs/OPERATIONS.md`・`frontend/README.md` | 残して、自分の変更に合わせて書き足す（CLAUDE.md「変更したら必ず更新するドキュメント」） |

### 2.5 見本を消す

自分の最初の機能ができたら、見本を消す。残しておくと、使わない画面・権限・表が本番に出たままになる。

**アイテム（example）を消すとき**

1. `bounded_contexts/example/` を消し、`presentation/fastapi/app.py` の `items_router`、
   `migrations/env.py` と `tests/conftest.py` の `item_model` を外す
2. 表を消すマイグレーションを足す（`op.drop_table("items")`。CLAUDE.md「DDL 管理」）
3. 権限 `item:view` / `item:write` を `shared/domain/auth/master_data.py` から外し、同じマイグレーションで
   `permissions` の行と付与を消す
4. 画面: `frontend/src/pages/ItemsPage.tsx`・`App.tsx` の経路・`components/Sidebar.tsx` の項目・`i18n` の `items.*`
5. コンテンツ設定の見本 `item_list_order` を `definitions.py` から外す（読む側が無くなるため）
6. 文書: `docs/ER.md`・`frontend/README.md`（4 か所）・ADR-0084 §2 の表の行

**共有メモ（notes）を消すとき**も同じ順で、`bounded_contexts/notes/`・`notes_router`・`note_model`・
表 `notes`・権限 `note:view` / `note:write`・`NotesPage.tsx` を外す。

消したあとは、試験の中で見本を使っている箇所も直す（`tests/integration/api/test_items.py` など）。
CI が落ちた箇所を順に直せば漏れない。

---

## 3. 機能を足す

### 3.1 新しい業務（コンテキスト）を足す

1. `bounded_contexts/<context>/` に 4 層を作る。手本は `bounded_contexts/example/`（小さな機能）と
   `bounded_contexts/notes/`（1 件ずつ可否が変わる機能）。層の決まりは [ARCHITECTURE.md](ARCHITECTURE.md)
2. ルーターを `presentation/fastapi/app.py` に足す
3. 選択肢のある決定は ADR に書く（`docs/decisions/ADR-template.md`）

### 3.2 表を足す

1. モデルを `bounded_contexts/<context>/infrastructure/` に置き、**区分を宣言する**
   （`declared(Tenancy.TENANT / PERSONAL / GLOBAL)`。迷ったら `TENANT`。ADR-0079 §2）
2. テナントの表は `tenant_id` を持ち、リポジトリはテナントをコンストラクタで受け取る
3. `migrations/env.py` と `tests/conftest.py` に、モデルを**参照する形で**登録する
4. マイグレーションを足し、`docs/ER.md` を同じコミットで直す

### 3.3 権限とロールを足す

1. **先に ADR-0084 §1（アクター）と §2（ユースケース）の表に行を足す。** そこから権限とロールを導く
2. 権限は `<対象>:<操作>`。見ると変えるを `:view` / `:write` に分け、`:write` を持つロールには `:view` も持たせる
3. `shared/domain/auth/master_data.py` の `PERMISSION_CODES` と `ROLE_PERMISSIONS` に足す。アプリ全体に効く権限は
   `SYSTEM_PERMISSIONS` にも入れる（入れないとテナント管理者が配れる）
4. マイグレーションを足し、`seed_master_data` **だけ**を呼ぶ（`ensure_default_admin` は呼ばない。ADR-0078 §3）
5. API には `Depends(require_permission("<権限>"))` を付ける。ロール名で分岐しない

### 3.4 画面を足す

1. `frontend/src/pages/` に画面を置き、`App.tsx` に経路、`components/Sidebar.tsx` に項目（必要な scope で出し分ける）
2. 文言は `i18n/en.json` と `ja.json` の両方に足す（API はエラーコードだけを返し、文言は画面が持つ）
3. `frontend/README.md` の 4 か所（画面遷移図・画面一覧・画面仕様・操作マニュアル）を直す

### 3.5 設定を足す

| 何の設定か | 足す場所 |
|---|---|
| アプリ全体の設定（システム設定。運用者が変える） | CLAUDE.md「設定管理」の 3 ファイル |
| テナントごとの決まり（コンテンツ設定。テナント管理者とコンテンツ管理者が変える） | `bounded_contexts/content_settings/domain/definitions.py` と、`i18n` の `contentSettings.field.<キー>`（ADR-0085） |

### 3.6 監査ログの種類を足す

`bounded_contexts/audit/domain/entities/audit_event.py` の `AuditEventType` に足し、
`tests/unit/domain/test_audit_event.py` の固定の一覧にも足す（値は記録として残るので変えない）。
`reason` には変えた項目名や失敗の分類だけを入れ、値（PII）は入れない。

---

## 4. 配る

- main へマージすると、deck が build → pin → deploy を走らせる（`resources/projects.json` に載せた環境）。
  手で上げるときは deck の画面から。
- 配った版の確かめ方・戻し方: [OPERATIONS.md「デプロイした版を確認したいとき」](OPERATIONS.md)・
  [「前の版へ戻したいとき」](OPERATIONS.md)
- 手元でビルドや試験を回す前に: CI が同じゲートを流す。PR を出して CI の結果で判断してよい。

---

## 5. 雛形の更新を取り込む

派生アプリは雛形の変更を**自動では受け取らない**。取り込むときは次のとおり。

```bash
git remote add template https://git.nolumia.com/kyon/fastapitemplate.git   # 最初の 1 回だけ
git fetch template
git switch -c chore/template-update origin/main
git merge template/main      # 衝突を解いて PR を出す
```

- **何が変わったかは、雛形の `docs/CHANGELOG.md` で読む。** 「派生アプリは〜」と書いてある項目は手当てが要る。
- **ぶつかりやすい場所**: `shared/domain/auth/master_data.py`（権限とロール）・`frontend/src/i18n/*.json`・
  `components/Sidebar.tsx`・`docs/` の文書。どちらの変更も残す形で解く。
- ⚠ **マイグレーションの頭が 2 つになる。** 自分のマイグレーションと雛形のマイグレーションが同じ版から
  枝分かれするので、取り込んだあと `uv run alembic heads` が 2 つを返す。`uv run alembic merge -m "merge template" <頭1> <頭2>`
  で合流のマイグレーションを足す。
- **ADR の番号がぶつかる。** 雛形の新しい ADR は、自分の続きの番号で取り込み、本文に「雛形の ADR-NNNN」と元の番号を書く。
- 取り込みを長く溜めない。差が大きいほど衝突が増える。

---

## 6. 雛形そのものを直す

派生アプリで見つけた不具合や、どのアプリにも要る機能は、**この雛形に先に入れて**から派生アプリへ取り込む。
派生アプリだけで直すと、次に作るアプリで同じ不具合を踏む。直すときの規則は CLAUDE.md にある。
