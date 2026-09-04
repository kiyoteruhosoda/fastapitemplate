# ADR-0025: 外部 IdP との SSO を OIDC 認可コードフロー（PKCE）で足し、ローカル認証は残す

- 日付: 2026-09-04
- 状態: 提案

## 文脈

このテンプレートのログインはローカルの JWT 認証だけで、外部 IdP との連携を持たない。
ADR-0002 は「外部 IdP 連携（当時の言い方では Google OAuth）はスコープ外」としていた。

その保留は、派生側で 3 回別々に解かれている。

| 派生 | 置き場所 | 経路 | クライアント認証 |
|---|---|---|---|
| nolumiawiki | `bounded_contexts/identity_federation/` | `/api/auth/sso/*` | `client_secret_basic` / `private_key_jwt` |
| rewardpointsweb | `bounded_contexts/identity_federation/` | `/api/auth/sso/*` | `client_secret_basic` / `private_key_jwt` |
| photonest | `bounded_contexts/federation/` | `/api/auth/oidc/*` | `private_key_jwt` |

前の 2 つは**同じ形にたどり着いていて、人のログインに関わるコードはほぼ一致する**
（差分は nolumiawiki 側の機械トークン検証だけで、`OidcProviderGateway` を比べると
それ以外の行は同一）。3 つ目は経路の名前から違う。**同じ設計判断が 3 回繰り返され、
3 回目で食い違いが出ている。** 原因はテンプレートに無いことなので、ここへ入れる。

決めることは 5 つある。プロトコルと経路 / IdP の持ち方 / IdP から戻ってきたものを
SPA へどう渡すか / アカウントとロールの決め方 / クライアント認証の方式。

## 決定

`bounded_contexts/identity_federation/` を足す。**nolumiawiki の実装を骨格として
逆輸入し**、人のログインまでを取り込む。

1. **認可コードフロー + PKCE（`S256`）。** 経路は `GET /api/auth/sso/provider`
   （ボタンを出すか）→ `GET /api/auth/sso/login`（送り出し）→
   `GET /api/auth/sso/callback`（戻り）→ `POST /api/auth/sso/token`（引き換え）の 4 つ。
   ID トークンは JWKS の公開鍵で署名を検証し、発行者・対象者・`nonce` まで確かめる。
   エンドポイントは discovery（`/.well-known/openid-configuration`）で引き、
   **文書が名乗る `issuer` が引きに行った先と一致すること**を確かめる。
   送り出しのときに合言葉を `SameSite=Lax` の Cookie で持たせ、戻りで照合する。
2. **IdP は 1 つで、設定（`OIDC_*`）から組み立てる。** 環境変数でも管理画面でも入る。
3. **コールバックは 1 回限りの引き換え券だけを URL に載せ**、SPA が
   `POST /api/auth/sso/token` でトークン対へ換える（券は SHA-256 で保存、既定 60 秒）。
4. **結び付けの鍵は `(issuer, sub)`。** 無ければ**検証済みの**メールアドレスで既存の
   ローカルアカウントへ寄せ、それも無ければ（`OIDC_AUTO_PROVISION` が真なら）作る。
   「受け入れてよい相手か」「寄せてよいか」の判断は `AccountLinkingPolicy`
   （rewardpointsweb 由来）、「作ってよいか・どのロールを与えるか」は
   `ProvisioningPolicy` / `RoleAssignment`（nolumiawiki 由来）が持つ。
5. **クライアント認証は `client_secret_basic`（既定）と `private_key_jwt` の 2 方式**を
   実装し、`OIDC_CLIENT_AUTH_METHOD` で選ぶ。**知らない値は既定へ落とさず「不備」**
   として扱う（SSO が無効になり、ログイン画面にボタンが出ない）。

**ローカル認証（パスワード・TOTP・パスキー）は残す。SSO は追加の入口。**
両者の関係は ADR-0026 で別に決める。

**テンプレートの既定は `OIDC_ENABLED=false`** ＝ 何も設定しなければ今までどおり。
併せて `OIDC_AUTO_PROVISION` の既定も **`false`** にする（nolumiawiki は `true`）。

機械の口（`client_credentials` で得たトークンでアプリの API を叩く経路）は
**今回に含めない**。

## 理由

- **逆輸入であって新規設計ではない。** 2 つの派生が同じ形へ独立に収束していて、
  片方は本番（`wiki.nolumia.com`）で動いている。ここで別の形を発明する理由が無い。
  骨格を nolumiawiki にしたのは、機能として上位集合だから（プロビジョニング・
  ロール写像・`private_key_jwt`）。ただし**「寄せてよいか」の判断を値オブジェクトに
  切り出した形は rewardpointsweb のほうが良い**ので、そこは後者を採る。
- **経路は `/api/auth/sso/*`。** 3 つのうち 2 つがこれで、`oidc` はプロトコルの名前
  でしかない。連携先が別の方式へ替わっても画面と経路の名前が嘘にならないほうを採る。
  photonest の `/api/auth/oidc/*` は、テンプレートへ寄せるときに移行の手当てが要る（影響）。
- **認可コードフロー + PKCE。** 暗黙フローはトークンがブラウザの URL を通り、履歴・
  Referer・アクセスログに残る。PKCE は公開クライアントのためのものだが、秘密を持つ
  クライアントでも認可コードの横取りを防ぐので常に付ける（`plain` は使わない）。
- **引き換え券。** 素直な代案 2 つはどちらも採らない。*トークンを URL に載せる* は
  履歴・Referer・アクセスログに残る。*Cookie だけでログイン状態にする* は、
  フロントエンドが localStorage のトークンでログイン済みかを判断している現状
  （T12 は未決）を先取りしてしまう。券なら T12 がどちらへ決まっても壊れない。
- **`state` だけでは「同じブラウザか」が分からない。** 控えは全員で 1 つの表を共有
  するので、`state` を知っている相手なら誰でも戻りを完了できる。攻撃者が自分で始めた
  認可要求の URL を踏ませると、**被害者は攻撃者としてログインした状態**になる
  （ログイン CSRF）。合言葉の Cookie を持たせ、控えにはハッシュだけを置いて照合する。
  `SameSite=Strict` にはできない——IdP からの戻りは別サイトからの GET の画面遷移で、
  `Strict` では Cookie が送られず正規のログインが必ず失敗する。
- **鍵は `sub`、メールアドレスは手掛かり。** メールアドレスは変わり得るので鍵にできない。
  一方、初回に「同じ人の既存アカウント」を見つける材料はそれしか無い。**検証済み
  （`email_verified`）に限る**のは、検証していないアドレスで寄せると、相手のアドレスを
  名乗るだけで他人のアカウントへ入れてしまうため。
- **`private_key_jwt` を最初から入れる。** `client_secret` は「どこに置いても平文の
  写しが増える」性質がある（Komodo の Variable はスタックへ `.env` として平文で
  書き出され、管理画面から入れた値は `system_settings` に平文で残る）。秘密鍵方式なら
  設定に載るのは**在り処**だけで、鍵はホストの外へ出ない。既定を
  `client_secret_basic` にしたのは、秘密鍵方式に対応しない IdP へつなぐ派生もあるため。
- **既定を `OIDC_ENABLED=false` に。** テンプレートは連携先を知らない。設定が空のまま
  有効になると、起動はするがログインだけが失敗する状態になる。
- **`OIDC_AUTO_PROVISION` の既定は `false`。** IdP がテナント共用のとき、`true` は
  「IdP に口座がある人は全員このアプリに入れる」を意味する。WBS は実際にこの理由で
  `false` にしている。テンプレートの既定は安全側へ倒し、開けたい派生が開ける。
- **機械の口を含めない。** `client_credentials` のトークンには認可が載らない
  （`scope` は空、`sub` はクライアント自身）ため、「誰として何をしてよいか」を
  受け側で決める設計がもう一段要る。人のログインと寿命の違う話なので分ける。

## 影響

- **テーブルが 3 つ増える**（`federated_identities` / `sso_login_sessions` /
  `sso_login_tickets`）。控えと券は期限切れを発行のたびに掃除するので定期ジョブは持たない。
  `docs/ER.md` の更新が要る。
- **設定キーが約 20 増える**（`OIDC_*`）。設定管理の 3 ファイルすべてを更新する。
- **`httpx` が実行時の依存に加わる**（discovery・トークン交換・UserInfo）。
- **画面が 1 つ増える**（SSO コールバック）。ログイン画面にボタンが増える。
  `frontend/README.md` の 4 か所を更新する。
- **SSO で作った利用者にパスワードは無い**（推測できない乱数のハッシュを入れる）。
  パスワードリセットを通せばローカルでも入れるようになる。ADR-0026 と関係する。
- **IdP 側のクライアント登録が要る。** 自前 idp では管理 API（`POST /admin/clients`）で
  登録でき、リダイレクト URI に `<APP_BASE_URL>/api/auth/sso/callback` を入れる。
- **`private_key_jwt` を使う場合、秘密鍵を read-only で渡す。** ファイルとディレクトリの
  **両方**でコンテナの実行 gid が通ること（通っていないと、起動も設定画面も通るのに
  利用者が IdP から戻ってきた瞬間だけ落ちる。起動時に一度読んでログへ出す）。
- **photonest は経路名が違う**（`/api/auth/oidc/*`）。テンプレートへ寄せるときは、
  IdP 側に登録済みのリダイレクト URI を差し替えるか、旧経路を残す手当てが要る。
- ADR-0002 の「外部 IdP 連携はスコープ外」を置き換える。サービスアカウント認証
  （機械の口）は引き続きスコープ外。
