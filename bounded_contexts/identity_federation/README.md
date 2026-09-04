# identity_federation — 外部 IdP との ID 連携（SSO）

社内の IdP（OpenID Provider）で本人を確かめ、**このアプリの利用者を決める**まで。
トークンの発行はこのコンテキストの外（`presentation/fastapi/services/token_service.py`）で、
認可（scope）の仕組みも変えない。IdP のグループは**ロール**へ写すだけで、
権限はそのロールが持つものになる。

設計判断は ADR-0025（方式）と ADR-0026（ローカル認証との併存）。

## 構成

```
domain/          連携先・クレームの対応付け・受け入れ方針・往復状態と券。
                 プロトコルの実装（HTTP / JWT）には依存しない
application/     ユースケース（開始・完了・引き換え・利用者の決定）
infrastructure/  SQLAlchemy モデルとリポジトリ、httpx + PyJWT の実装
presentation/    API ルーター・スキーマ・依存の組み立て・往復状態の Cookie
```

## ログインの往復

```
ブラウザ                    このアプリ                        IdP
   │  GET /api/auth/sso/login  │                               │
   │──────────────────────────>│ state / nonce / PKCE を作る    │
   │<── 303 + Set-Cookie ──────│ （署名して Cookie に載せる）    │
   │  認可エンドポイントへ ──────────────────────────────────────>│
   │<────────────────────────── 303（code & state）─────────────│
   │  GET /api/auth/sso/callback │                             │
   │── Cookie 同送 ───────────>│ 復元して照合 → コードを交換 ──>│
   │                           │<── ID トークン（JWKS で検証）───│
   │<── 303 /login/sso?ticket= │ 利用者を決めて引き換え券を発行  │
   │  POST /api/auth/sso/token │                               │
   │──────────────────────────>│ 券を消費 → access / refresh    │
```

**認可コードフロー + PKCE（`S256`）**。暗黙フローは使わない——ID トークンが
ブラウザの URL を通り、履歴・アクセスログに残るため。

**往復状態（`state` / `nonce` / `code_verifier`）は署名付き Cookie（`sso_tx`）で運ぶ。**
サーバー側に控えを置かない。表に控えを置く形だと控えは全員で 1 つの表を共有するので、
`state` を知っているだけの相手でも戻りを完了できてしまう ——攻撃者が始めた認可要求を
被害者に踏ませると、被害者は**攻撃者として**ログインした状態になる（ログイン CSRF）。
Cookie なら**照合対象そのものが被害者のブラウザに存在しない**ので、同じ防御が 1 つの
仕組みで成立し、保管も掃除も要らない。

- 署名は内蔵 JWT と同じ `JWT_SECRET_KEY`（HS256）。中身は読めるが書き換えられない。
- `HttpOnly`。`code_verifier` を持つので JavaScript から読めてはならない。
- `SameSite=Lax`。IdP からの戻りは別サイトからの GET の画面遷移で、`Strict` では
  送られず正規のログインが必ず失敗する。
- 往復が終わったら成功・失敗どちらでも落とす。

⚠ **Cookie を落とすブラウザでは SSO でログインできない**（`sso_state_invalid`）。
自サイトの Cookie なのでサードパーティ Cookie の制限とは別だが、Cookie を一切拒否する
設定では通らない。

**引き換え券（`sso_login_tickets`）は 1 回限り・短命（既定 60 秒）で、
ハッシュだけを保存する。** 戻りは画面遷移なので SPA は応答本文を読めないが、
トークンを URL に載せると履歴・Referer・アクセスログへ残る。

## 要求した認証の強度

`OIDC_ACR_VALUES` を入れると認可要求に `acr_values` が載り、**戻ってきた ID トークンの
`acr` を突き合わせる**（ADR-0026 決定 1）。一致しなければ、また **`acr` が返って
こなければ**ログインを断る（`sso_acr_not_satisfied`）。

要求を送るだけで結果を見ないと、IdP 側のポリシーの綴り違い 1 つで「MFA を要求した
つもりで単要素のログインを受け取る」状態になり、しかもそれに気付けない。既定は空
（要求しない）なので、**設定した派生だけが fail closed になる**。

⚠ **`amr` は使わない。** RFC 8176 の `amr` は使われた方式の一覧であって強度ではない。
外部 IdP 経由（`fed`）はその先で何が使われたかを IdP 自身も知らない。

## ID トークンの検証

`iss` / `aud` / `exp` に加えて **`nonce` を必ず照合する**（別の場面で取った
ID トークンを持ち込むリプレイを止めるため）。署名鍵は JWKS から引き、
**受け入れるアルゴリズムは非対称鍵のみ**（`HS*` はクライアントシークレットが鍵に
なるため、IdP 以外も署名を作れてしまう）。

グループやメールアドレスを ID トークンに載せない IdP のために UserInfo も引く。
`sub` が食い違う応答は捨てる（別人の情報で上書きされないように）。

## アカウントの決まり方

1. `(issuer, sub)` の結び付きがあればその利用者（`federated_identities`）
2. 無ければ**検証済みの**メールアドレスで既存のローカルアカウントへ寄せる
3. それも無ければ（`OIDC_AUTO_PROVISION` が真なら）作る

**メールアドレスは鍵にしない**（変わり得るため）。手掛かりとして使うのは初回だけで、
**検証済み（`email_verified`）に限る**——検証していないアドレスで寄せると、相手の
アドレスを名乗るだけで他人のアカウントを乗っ取れる。

同じアドレスの利用者が既に居て、それでも寄せてよくない場合（`email_verified` が
偽・`OIDC_LINK_BY_EMAIL` が偽）は `sso_account_not_linked` として**断る**。
`users.email` は一意なので、ここで作り直すと一意制約に当たる。

ロールは `OIDC_ROLE_MAPPING`（`"<グループ>=<ロール>"`）と `OIDC_DEFAULT_ROLES` で
決まる。既定では**作るときにだけ**与える。`OIDC_ROLE_SYNC` を有効にすると毎回
引き直すが、**1 つも当たらないときは触らない**（クレーム名の書き損じで全員が
権限を失うのを避ける）。

## トークンエンドポイントへの名乗り方

方式は 2 つあり、`OIDC_CLIENT_AUTH_METHOD` で選ぶ（ADR-0025 決定 5）。方式とその材料は
`ClientCredential` 値オブジェクトが持ち、**「揃っているか」の判断も方式ごとに違う**
ので、そこに置いてある。

| 方式 | 送るもの | 設定に載るもの |
|---|---|---|
| `client_secret_basic`（既定） | Basic 認証（IdP が受けなければ本文へ） | 秘密そのもの |
| `private_key_jwt` | 秘密鍵で署名したアサーション（RFC 7523） | 鍵の在り処と `kid` だけ |

**秘密鍵は署名のときに読む**（`infrastructure/client_assertion.py`）。読めなければ
`SsoNotConfiguredError`。⚠ この失敗は使うまで起きないので、**起動時にも一度読んで
ログへ出している**（`presentation/startup_check.py`）。権限が合っていないと、
起動も設定の確認も通るのに IdP から戻ってきた瞬間だけ落ちる。

## 失敗の返し方

`/login` と `/callback` はブラウザの画面遷移なので、失敗も**ログイン画面への転送**
（`/login?sso_error=<code>`）で返す。JSON を返しても SPA は読めない。IdP が返した
文字列をそのまま載せないよう、`[a-z_]{1,64}` に当たらないコードは `sso_error` へ倒す。
`POST /token` だけは JSON で、対応付けは `presentation/error_handling.py`。

## 拡張するときの注意

- **知らない認証方式は既定へ落とさない**（不備として SSO ごと無効になる）。
  黙って `client_secret_basic` にすると、IdP からは理由の分からない
  `invalid_client` が返るだけになる。
- **連携先は 1 つ**で、設定（`OIDC_*`）から `IdentityProvider` を起こしている
  （`presentation/dependencies.py`）。複数 IdP が要るようになったら、そこの出所を
  テーブルへ差し替える。ユースケースは値オブジェクトしか知らないので変えずに済む。
- `OidcProviderGateway` は Domain 層のインターフェース。実装を差し替えるときは
  `presentation/dependencies.py` の `oidc_gateway` を変える（テストは
  `app.dependency_overrides` で差し替えている）。
- **SSO で作った利用者にパスワードは無い**（推測できない乱数のハッシュが入る）。
