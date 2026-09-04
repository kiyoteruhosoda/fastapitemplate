"""ID 連携コンテキストのドメイン例外。

``code`` がそのまま API のエラーコード（表示文言はフロントエンド）になる。
ブラウザの往復の途中で起きた失敗は、ログイン画面へ ``?sso_error=<code>`` として
返る（ADR-0025）。
"""

from __future__ import annotations


class IdentityFederationError(Exception):
    """このコンテキストの基底例外。"""

    code = "sso_error"


class SsoNotConfiguredError(IdentityFederationError):
    """SSO が無効、または接続先（issuer / client）が埋まっていない。"""

    code = "sso_not_configured"


class SsoLoginTransactionInvalidError(IdentityFederationError):
    """往復状態が復元できない（Cookie が無い・期限切れ・``state`` の不一致）。

    **Cookie を落とすブラウザではここで必ず止まる。** 自サイトの Cookie なので
    サードパーティ Cookie の制限とは別だが、Cookie を一切拒否する設定では
    正規のログインも通らない（ADR-0025）。
    """

    code = "sso_state_invalid"


class SsoTicketNotFoundError(IdentityFederationError):
    """引き換え券が見つからない（期限切れ・使用済み）。"""

    code = "sso_ticket_invalid"


class IdentityProviderUnavailableError(IdentityFederationError):
    """IdP と話せない（discovery・トークン交換の通信／応答の失敗）。"""

    code = "sso_provider_unavailable"


class InvalidIdTokenError(IdentityFederationError):
    """ID トークンの検証に失敗した（署名・発行者・対象者・nonce）。"""

    code = "sso_invalid_id_token"


class SsoAcrNotSatisfiedError(IdentityFederationError):
    """要求した認証の強度（``acr_values``）が満たされていない（ADR-0026 決定 1）。

    ``acr`` が返ってこない場合もこれになる。要求したのに保証が得られていない以上、
    通してはいけない。
    """

    code = "sso_acr_not_satisfied"


class SsoEmailMissingError(IdentityFederationError):
    """メールアドレスのクレームが無い（アカウントを結び付けられない）。"""

    code = "sso_email_missing"


class SsoEmailNotAllowedError(IdentityFederationError):
    """許可されていないメールドメイン。"""

    code = "sso_email_not_allowed"


class SsoAccountNotLinkedError(IdentityFederationError):
    """対応するアカウントが無く、自動作成も許可されていない。"""

    code = "sso_account_not_linked"


class SsoAccountInactiveError(IdentityFederationError):
    """アカウントが無効化されている。"""

    code = "sso_account_inactive"


__all__ = [
    "IdentityFederationError",
    "IdentityProviderUnavailableError",
    "InvalidIdTokenError",
    "SsoAccountInactiveError",
    "SsoAccountNotLinkedError",
    "SsoAcrNotSatisfiedError",
    "SsoEmailMissingError",
    "SsoEmailNotAllowedError",
    "SsoLoginTransactionInvalidError",
    "SsoNotConfiguredError",
    "SsoTicketNotFoundError",
]
