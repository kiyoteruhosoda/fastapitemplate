"""OpenID Provider との往復のインターフェース（実装は Infrastructure 層）。

プロトコルの細部（discovery・トークンエンドポイント・JWKS による署名検証）は
実装側に閉じ込め、ドメインとアプリケーションは「認可 URL を作る」「認可コードを
クレームへ換える」の 2 つだけを知る。返すのは**検証済みの**クレームで、素の
``dict`` として扱う（HTTP・JWT ライブラリの型を内側へ持ち込まない）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)


@dataclass(frozen=True)
class AuthorizationRequest:
    """IdP へブラウザを送り出すための材料。"""

    provider: IdentityProvider
    state: str
    nonce: str
    code_challenge: str
    #: 要求する認証の強度（``acr_values``）。空 = 要求しない（ADR-0026 決定 1）。
    acr_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class EndSessionRequest:
    """サインアウトを IdP まで通すための材料（RP-Initiated Logout 1.0）。

    ``id_token_hint`` は載せない。このテンプレートは検証したあとの ID トークンを
    保持しないので、**手元に無いものを送れない**。代わりに ``client_id`` と
    ``post_logout_redirect_uri`` の組で名乗る（OP はこの組で登録済みかを見る）。
    保持するなら行を 1 本増やす話になるので、必要になったアプリで別途決める。
    """

    provider: IdentityProvider
    #: サインアウト後に戻ってくる先。空なら付けない（OP 自身の完了ページで止まる）。
    post_logout_redirect_uri: str = ""


@dataclass(frozen=True)
class LogoutTokenVerification:
    """IdP から届いた ``logout_token`` を確かめるための材料（ADR-0036）。"""

    provider: IdentityProvider
    logout_token: str


@dataclass(frozen=True)
class CodeExchange:
    """戻ってきた認可コードを引き換えるための材料。"""

    provider: IdentityProvider
    code: str
    code_verifier: str
    nonce: str


class OidcProviderGateway(Protocol):
    def authorization_url(self, request: AuthorizationRequest) -> str:
        """認可エンドポイントへの URL を組み立てる。

        IdP と話せない場合は
        :class:`~bounded_contexts.identity_federation.domain.exceptions.IdentityProviderUnavailableError`。
        """

    def end_session_url(self, request: EndSessionRequest) -> str | None:
        """サインアウトのために送り出す URL。**IdP が対応していなければ ``None``。**

        discovery に ``end_session_endpoint`` が無い OP があるので、呼ぶ側は
        ``None`` を「この IdP では通せない」として素直に扱うこと（失敗にしない）。
        """

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        """認可コードを検証済みのクレームへ換える。

        ID トークンの署名・発行者・対象者・``nonce`` まで確かめたうえで返す。
        失敗は ``InvalidIdTokenError`` / ``IdentityProviderUnavailableError``。
        """

    def verify_logout_token(self, verification: LogoutTokenVerification) -> Mapping[str, Any]:
        """``logout_token`` の署名・発行者・対象者・期限を確かめてクレームを返す。

        ID トークンと同じ鍵・同じ発行者・同じ対象者なので、**JWT として確かめられる
        ことはここまで**。「ログアウトの通知であること」の判断は
        :class:`~bounded_contexts.identity_federation.domain.value_objects.logout_notice.LogoutNotice`
        が行う。失敗は ``InvalidLogoutTokenError`` / ``IdentityProviderUnavailableError``。
        """


__all__ = [
    "AuthorizationRequest",
    "CodeExchange",
    "EndSessionRequest",
    "LogoutTokenVerification",
    "OidcProviderGateway",
]
