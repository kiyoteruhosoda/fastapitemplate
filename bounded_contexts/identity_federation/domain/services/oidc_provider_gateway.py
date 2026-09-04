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

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        """認可コードを検証済みのクレームへ換える。

        ID トークンの署名・発行者・対象者・``nonce`` まで確かめたうえで返す。
        失敗は ``InvalidIdTokenError`` / ``IdentityProviderUnavailableError``。
        """


__all__ = [
    "AuthorizationRequest",
    "CodeExchange",
    "OidcProviderGateway",
]
