# account_security — アカウントセキュリティ

利用者が自分のアカウントを守るための「第二の要素」を扱うコンテキスト。
二要素認証（TOTP）とパスキー（WebAuthn）の 2 つを持つ。

パスワードそのもの（保存・変更・リセット）はこのコンテキストの外
（`presentation/fastapi/routers/auth.py` と `shared/`）。ここが扱うのは
「パスワードに加えて／代わりに本人を確かめる手段」に限る。

## 構成

```
domain/          TOTP 共有鍵・パスキー・チャレンジと、その永続化／外部処理の
                 インターフェース（pyotp / webauthn には依存しない）
application/     ユースケース（登録の 2 段階、ログイン時の検証、一覧・削除）
infrastructure/  SQLAlchemy モデルとリポジトリ、pyotp / py_webauthn の実装
presentation/    API ルーター・スキーマ・依存の組み立て
```

## 二要素認証（TOTP）

登録は**必ず 2 段階**で行う。

1. `POST /api/account/security/two-factor/enrollment` — 共有鍵と QR を返す。
   この時点では `confirmed_at` が NULL で、二要素認証はまだ**有効ではない**。
2. `POST /api/account/security/two-factor/confirmation` — 認証アプリのコードを
   1 度検証できたら有効にする。

1 段階で有効にすると、QR の読み取りに失敗した利用者が自分のアカウントから
締め出される。未確認の登録が残った状態でログインしてもコードは要求しない。

解除（`.../two-factor/removal`）にも現在のコードを要求する。セッションを
奪われただけで第二要素を外せると、二要素認証の意味が薄れるため。

ログインでは `POST /api/auth/login` の `totp_code` を検証する。未提示なら
`totp_required`、不一致なら `invalid_totp` を 401 で返す。

## パスキー（WebAuthn）

チャレンジは **DB（`webauthn_challenges`）に保存する**。Gunicorn は複数ワーカーで
動くため、発行したプロセスと検証するプロセスが一致しない。プロセスのメモリに
置くと、ワーカーをまたいだ瞬間に検証が失敗する。

利用者へ返すのは `challenge_id` だけで、チャレンジ本体は往復させない。
チャレンジは 1 回消費すると削除され、期限切れ（既定 300 秒）のものは新しい
チャレンジを発行するたびにまとめて掃除する。

ログイン用チャレンジは `allowCredentials` を空にして発行する。認証器が自分で
資格情報を選ぶため、メールアドレスを入力せずにログインできる。誰のパスキーかは
返ってきた資格情報 ID から特定する。

`WEBAUTHN_RP_ID` は登録済みパスキーの結び付け先。変更すると既存のパスキーは
すべて無効になる。

パスキーでログインした場合、TOTP は要求しない。パスキーは所持（認証器）と
（多くの端末では）生体・PIN を伴う単独で強い認証手段であり、その上でさらに
TOTP を課す設計は採らない。

## 拡張するときの注意

`TotpAuthenticator` / `WebAuthnRelyingParty` は Domain 層のインターフェース。
実装を差し替えるときは `presentation/dependencies.py` の
`build_totp_authenticator` / `build_relying_party` を変える（テストは
`app.dependency_overrides` で差し替えている）。
