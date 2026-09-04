# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

- 状態: ⬜未着手 / 🚧進行中 / 🟡要判断
- 影響度・工数: 大 / 中 / 小

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T2 | 既定のままの秘密鍵で本番起動するのを止める（未使用 `SECRET_KEY` の整理も） | ⬜未着手 | 大 | 小 |
| 2 | T3 | ログイン試行の回数制限とアカウントロック | ⬜未着手 | 大 | 中 |
| 3 | T4 | 最後の管理者を失う操作を防ぐ | ⬜未着手 | 大 | 小 |
| 4 | T5 | 発行済みトークンを失効させる手段 | ⬜未着手 | 大 | 大 |
| 5 | T6 | 一覧 API のページング規約を決めて見本を置く | ⬜未着手 | 中 | 中 |
| 6 | T7 | 公開面の露出を絞る（`/metrics`・`/info`・nginx のヘッダー） | ⬜未着手 | 中 | 小 |
| 7 | T8 | 依存ライブラリの脆弱性検査を CI に足す | ⬜未着手 | 中 | 小 |
| 8 | T9 | 期限切れ・使用済みパスワードリセットトークンを掃除する | ⬜未着手 | 中 | 小 |
| 9 | T10 | `example` コンテキストを「作って終わり」から本当の見本へ育てる | ⬜未着手 | 中 | 中 |
| 10 | T11 | テンプレート名を付け替えるスクリプト | ⬜未着手 | 中 | 中 |
| 11 | T12 | フロントエンドのトークン保管方式を 1 つに決める | 🟡要判断 | 中 | 中 |
| 12 | T15 | 機械の口（`client_credentials` のトークンで API を叩く経路） | 🟡要判断 | 中 | 大 |

## 詳細

### T2 既定のままの秘密鍵で本番起動するのを止める

`JWT_SECRET_KEY` の既定値は `system_settings_defaults.py` の
`"default-jwt-secret-change-me-in-production"` で、`.env.example` の該当行は
コメントアウトされている。つまり **何も設定しなくても起動し、誰でも偽造できる
署名鍵でトークンを発行し続ける**。テンプレートとしていちばん踏みやすい落とし穴なので、
起動時に「既定値のまま かつ 本番」を検出して落とす（あるいは起動を拒否して
明示的に生成を促す）ようにする。

同時に `SECRET_KEY` を整理する。設定として定義され `.env.example` にも載っているが、
`settings.secret_key` を読んでいるコードはどこにも無い（署名は `jwt_secret_key`
のみ）。使わないなら消す、使うなら用途を書く。

### T3 ログイン試行の回数制限とアカウントロック

`/api/auth/login`・`/api/auth/forgot-password`・パスキーの認証開始のいずれにも
回数制限が無く、失敗を監査ログに残すだけで何度でも試せる。nginx 側にも `limit_req`
は入っていない。テンプレートの既定として、少なくともログインには失敗回数に応じた
待ち時間かロックが要る。

併せて、`LoginService.authenticate` は未知のメールアドレスならパスワード照合を
せずに即座に返す。応答本文は `invalid_credentials` に揃っていても**応答時間で
アカウントの存在が分かる**ため、存在しない場合もダミーのハッシュ照合を通す。

### T4 最後の管理者を失う操作を防ぐ

`/api/admin/users` の更新・削除に、自分自身と「最後の `user:manage` 保有者」を
守る条件が無い。管理者が自分を削除する・自分を `is_active=false` にする・自分から
admin ロールを外す、のいずれでも**誰も管理画面に入れない状態**を作れる。
`docs/OPERATIONS.md` には「管理者が 1 人しかいないとき」の復旧手順（コンテナ内から
スクリプトを流す）があるが、そもそも作れないようにするほうが先。

### T5 発行済みトークンを失効させる手段

JWT は完全にステートレスで、失効の手段が「有効期限切れを待つ」しか無い。

- `/api/auth/logout` は Cookie を消すだけ。手元に控えたトークンはそのまま使える。
- **パスワードを変えても既発行のトークンは無効にならない。** access は寿命（既定
  15 分）まで、refresh は既定 14 日まで通る。パスワードを変える動機の多くは
  「漏れたかもしれない」なので、ここが効かないのは痛い。
- refresh トークンのローテーションが無く、同じ refresh を何度でも使い回せる。

無効化（`is_active=false`）は例外で、既に即時に効く。access・refresh のどちらも
検証のたびに `_load_active_user` がユーザーを引き直し、`is_active` が落ちていれば
弾くため（`token_service.py`）。この仕組みに何を載せるかが設計の出発点になる。

`jti` + 失効リスト、あるいはユーザーごとのトークン世代（password_changed_at 等）を
検証に混ぜる方式を決めて入れる。方式は ADR に残す。

### T6 一覧 API のページング規約を決めて見本を置く

ログ検索（`bounded_contexts/audit/`）だけがページングを持ち、
`GET /api/admin/users`・`GET /api/admin/roles`・`GET /api/items` は全件を返す。
フロントエンドも全件を前提に描いている。テンプレートから作った先で必ず当たるので、
`limit` / `offset`（あるいはカーソル）と応答の形をテンプレートの規約として決め、
`example` に見本を置く。ADR で残す対象。

### T7 公開面の露出を絞る

- `/metrics`（Prometheus）と `/info`（バージョン・git SHA・ブランチ・ビルド時刻・
  環境名）が**未認証**で、同梱の nginx はすべてのパスを app へ素通しする。外向けに
  出す構成では、認証を要求するか nginx で内部ネットワークに限定する。
- nginx にセキュリティヘッダー（`X-Content-Type-Options` / `Referrer-Policy` /
  `X-Frame-Options` または CSP、HTTPS 終端をここで持つなら HSTS）が無い。
- ついでに SPA の静的資産（`/assets/*` はハッシュ付き）に長期キャッシュと gzip が
  効いていない。

### T8 依存ライブラリの脆弱性検査を CI に足す

CI は整形・静的解析・型・テストの 8 ゲートを持つが、依存の脆弱性は見ていない。
`pip-audit`（あるいは `uv` の監査）と `npm audit` を足し、Dependabot の設定
（`.github/dependabot.yml`）を置く。認証・パスキーを持つテンプレートなので、
派生プロジェクトが古い `webauthn` / `pyjwt` を抱えたまま増えるのは避けたい。

### T9 期限切れ・使用済みパスワードリセットトークンを掃除する

`webauthn_challenges` は発行のたびに期限切れを消しているのに、
`password_reset_tokens` は使用済み・期限切れの行が残り続ける。ログ保持期間
（ADR-0021）の定期実行に相乗りさせるのが素直。

### T10 `example` コンテキストを本当の見本へ育てる

README とルーターの docstring は「Item CRUD」と書いているが、実際にあるのは
作成と一覧だけで、更新・削除は無い（`bounded_contexts/example/application/use_cases/`
は `create_item.py` と `list_items.py` の 2 つ）。`items` テーブルにも
`created_at` / `updated_at` が無く、テンプレートが他所で守らせている時刻の規約を
見本自身が守っていない。**新機能を書く人が最初に読む場所**なので、更新・削除・
時刻・ページング・404 の返し方まで揃った見本にする（表記も実態に合わせる）。

### T11 テンプレート名を付け替えるスクリプト

CLAUDE.md・README・ADR-0023・OPERATIONS.md がかなりの分量を使って「名前を必ず
変えること」を説明しているのに、しかも **Komodo 方式では名前を間違えても自動で
止まらなくなった**（旧 ADR-0015 の中断機構を撤去した）のに、実際の
付け替えは手作業（`docker-compose.yml` の既定値、`Makefile` の `IMAGE`、
`deploy/komodo/` の雛形、`pyproject.toml`、`frontend/package.json`、`TOTP_ISSUER` /
`WEBAUTHN_RP_NAME`、`app.py` の `title`）。`scripts/rename_project.sh <new-name>`
を用意すれば、この文書量の大半が「これを実行する」の 1 行になる。

### T12 フロントエンドのトークン保管方式を 1 つに決める

バックエンドは access トークンを **httpOnly Cookie** に載せている
（`set_access_token_cookie`）のに、フロントエンドは同じトークンを
**localStorage** にも保存して `Authorization` ヘッダーで送っている
（`frontend/src/services/api.ts`）。httpOnly にした意味が localStorage 側で
打ち消されており、二重管理でもある。

- Cookie 一本にする → XSS でトークンを持ち出されない。CSRF 対策（`SameSite` に
  加えてトークン）と、Swagger UI からの手動確認の導線を決める必要がある。
- ヘッダー一本にする → 現状の実装に近いが、Cookie を発行する意味が無くなる。

どちらを採るかは影響範囲が広く、決めたら ADR に残す。

### T15 機械の口（`client_credentials` のトークンで API を叩く経路）

ADR-0025 では**含めない**と決めた。テンプレートへ入れるかどうかがまだ判断待ち。

`client_credentials` のトークンには**認可が載らない**（`scope` は空になり、`sub` は
利用者ではなくクライアント自身）。そのため「どのクライアントが誰として何をしてよいか」を
受け側で登録する仕組みが別に要る。nolumiawiki は `MachineClient.acts_as` でそれを
持っている（あちらの ADR-0060）。

判断すること:

- テンプレートに要るか。要るなら nolumiawiki の形をそのまま採るか。
- 検証で外せない点（`sub_type == "client"` と `sub == client_id` の確認）を、
  どのレイヤーの責務にするか。

（直近の完了分の要約は `CHANGELOG.md`、設計判断は `decisions/`（ADR）を参照。
テンプレート刷新の経緯は `history/2026-07-template-refresh.md`、
品質ゲート導入の経緯は `history/2026-07-quality-gates.md`）
