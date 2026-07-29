# ADR-0002: 認証の初期スコープは JWT + パスワードリセットとし、TOTP・パスキーは含めない

- 日付: 2026-07-17
- 状態: 一部廃止（TOTP・パスキーの除外は ADR-0003 で置き換え）

## 文脈

参照元の photonest は JWT に加えて TOTP（二要素認証）・パスキー（WebAuthn）・
Google OAuth・サービスアカウント認証を持つ。テンプレートの「基本的な認証」に
どこまで含めるかの判断が必要だった。

## 決定

初期スコープは以下とする:

- JWT（access / refresh）によるログイン・ログアウト
- ユーザー／ロール／権限（scope ベース認可）
- パスワード変更・パスワードリセット（email_sender コンテキスト + SMTP 設定）

TOTP・パスキー・Google OAuth・サービスアカウントは含めない。

## 理由

- パスワードリセットは大半のアプリで必要になるため、メール送信基盤
  （email_sender）ごと含めた方がテンプレートとしての実用性が高い。
- TOTP・パスキーは「基本的な認証」の範囲を超え、依存（pyotp / webauthn）と
  画面・テーブルが増える。必要になった時点で photonest の
  `bounded_contexts/totp/`・`presentation/fastapi/auth/passkeys.py` を移植する
  方が、テンプレートを薄く保てる。

## 影響

- `users` テーブル等に 2FA 用カラムは持たない。導入時はマイグレーション追加で対応。
- メール送信は SMTP 設定（システム設定画面で管理）が前提。未設定時は
  パスワードリセット API がエラーコードを返す。
- TOTP・パスキーはその後 ADR-0003 で取り込んだ（`bounded_contexts/account_security/`）。
  Google OAuth・サービスアカウント認証は引き続きスコープ外。
