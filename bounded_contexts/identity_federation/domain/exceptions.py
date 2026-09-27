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


class InvalidLogoutTokenError(IdentityFederationError):
    """``logout_token`` の検証に失敗した（署名・発行者・対象者・期限・形）。

    **理由は外へ出さない。** この口は未認証で叩けるので、細かく答えると
    「どこまで通ったか」を総当たりの手掛かりにできる。
    """

    code = "sso_invalid_logout_token"


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


class SsoIdentityTakenError(IdentityFederationError):
    """その IdP アカウントは**別の利用者**に結び付いている（ADR-0040）。

    ⚠ **横取りになるので断る。** 付け替えを許すと、IdP 側で 1 つの口座を共有して
    いる相手が、後からこのアプリの別人の入り口を奪える。
    """

    code = "sso_identity_taken"


class SsoAlreadyLinkedError(IdentityFederationError):
    """この利用者には、その IdP の結び付きが**既にある**（ADR-0040）。

    別の ``subject`` へ差し替えたいなら、いったん解除してから結び直す。黙って
    上書きすると、前の結び付きで入っていた経路が予告なく消える。
    """

    code = "sso_already_linked"


class SsoIdentityNotLinkedError(IdentityFederationError):
    """解除しようとしたが、その IdP との結び付きが無い。"""

    code = "sso_identity_not_linked"


class SsoLastEntranceError(IdentityFederationError):
    """解除すると、この利用者が**どこからも入れなくなる**（ADR-0040）。

    ⚠ **締め出しを作らない。** ローカルのパスワードもパスキーも無い利用者から
    IdP を外すと、残るのは管理者による復旧だけになる。
    """

    code = "sso_last_entrance"


class SsoLinkSessionMismatchError(IdentityFederationError):
    """連携の往復を始めた利用者と、戻ってきたときのセッションが違う。

    往復の途中でサインアウトした・別の利用者で入り直した場合に起きる。
    **どちらの口座へ結び付けるべきか決められない**ので、やり直してもらう。
    """

    code = "sso_link_session_mismatch"


class SsoAccountInactiveError(IdentityFederationError):
    """アカウントが無効化されている。"""

    code = "sso_account_inactive"


class MachineNotBoundToApplicationError(IdentityFederationError):
    """名乗ったサービスアカウントが、assay でどのアプリにも結び付いていない（管理 API の 403。ADR-0043）。

    ⚠ **障害ではなく「まだ準備されていない」。** どのアプリの名簿を返すかは assay が
    呼び出し元のサービスアカウントから決めるので、結び付けるまで毎回この形で返る。
    """

    code = "machine_not_bound_to_application"


__all__ = [
    "IdentityFederationError",
    "IdentityProviderUnavailableError",
    "InvalidIdTokenError",
    "InvalidLogoutTokenError",
    "MachineNotBoundToApplicationError",
    "SsoAccountInactiveError",
    "SsoAccountNotLinkedError",
    "SsoAcrNotSatisfiedError",
    "SsoAlreadyLinkedError",
    "SsoEmailMissingError",
    "SsoEmailNotAllowedError",
    "SsoIdentityNotLinkedError",
    "SsoIdentityTakenError",
    "SsoLastEntranceError",
    "SsoLinkSessionMismatchError",
    "SsoLoginTransactionInvalidError",
    "SsoNotConfiguredError",
    "SsoTicketNotFoundError",
]
