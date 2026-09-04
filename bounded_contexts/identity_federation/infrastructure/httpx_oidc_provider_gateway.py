"""OpenID Provider との往復（httpx + PyJWT）。

認可コードフロー + PKCE（``S256``）を実装する。暗黙フローは使わない——
ID トークンがブラウザの URL を通り、履歴とアクセスログへ残るため。

ID トークンは **JWKS の公開鍵で署名を検証**し、発行者・対象者・``nonce`` まで
確かめる。グループやメールアドレスを ID トークンに載せない IdP のために、
UserInfo も引いて足りないクレームを補う。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    InvalidIdTokenError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)
from bounded_contexts.identity_federation.infrastructure.client_assertion import (
    ASSERTION_TYPE,
    ClientAssertionRequest,
    build_client_assertion,
)
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import (
    USER_AGENT,
    OidcMetadataCache,
    ProviderMetadata,
)

logger = logging.getLogger(__name__)

_BASIC_AUTH = "client_secret_basic"


class HttpxOidcProviderGateway:
    def __init__(self, *, metadata: OidcMetadataCache | None = None, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds
        self._metadata = metadata if metadata is not None else OidcMetadataCache(timeout_seconds=timeout_seconds)

    # ------------------------------------------------------------------
    # 送り出し
    # ------------------------------------------------------------------

    def authorization_url(self, request: AuthorizationRequest) -> str:
        provider = request.provider
        metadata = self._metadata.metadata(provider.issuer)
        parameters = {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "scope": provider.scope_parameter,
            "state": request.state,
            "nonce": request.nonce,
            "code_challenge": request.code_challenge,
            "code_challenge_method": "S256",
        }
        if request.acr_values:
            # 空白区切り（OIDC Core §3.1.2.1）。要求しないときはパラメータごと出さない
            # ——空文字を送ると「空の要求」として扱う IdP がある。
            parameters["acr_values"] = " ".join(request.acr_values)
        separator = "&" if "?" in metadata.authorization_endpoint else "?"
        return f"{metadata.authorization_endpoint}{separator}{urlencode(parameters)}"

    # ------------------------------------------------------------------
    # 引き換え
    # ------------------------------------------------------------------

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        metadata = self._metadata.metadata(exchange.provider.issuer)
        response = self._request_token(metadata, exchange)
        id_token = response.get("id_token")
        if not isinstance(id_token, str):
            raise InvalidIdTokenError
        claims = self._verify(metadata, exchange, id_token)
        access_token = response.get("access_token")
        if isinstance(access_token, str) and metadata.userinfo_endpoint:
            return {**self._userinfo(metadata, access_token, claims), **claims}
        return claims

    def _request_token(self, metadata: ProviderMetadata, exchange: CodeExchange) -> dict[str, Any]:
        provider = exchange.provider
        form = {
            "grant_type": "authorization_code",
            "code": exchange.code,
            "redirect_uri": provider.redirect_uri,
            "code_verifier": exchange.code_verifier,
            "client_id": provider.client_id,
        }
        if provider.credential.uses_private_key:
            # 秘密鍵で署名したアサーションで名乗る（ADR-0025）。Basic は使わない。
            form.update(_assertion_fields(provider, metadata.token_endpoint))
            return self._post_form(metadata.token_endpoint, form, None)
        secret = provider.credential.secret
        if metadata.token_auth_methods and _BASIC_AUTH not in metadata.token_auth_methods:
            # Basic を受け付けない IdP には本文で送る（client_secret_post）
            form["client_secret"] = secret
            return self._post_form(metadata.token_endpoint, form, None)
        return self._post_form(metadata.token_endpoint, form, (provider.client_id, secret))

    def _decode(self, metadata: ProviderMetadata, token: str, **options: Any) -> dict[str, Any]:
        """署名鍵を引いて検証する。**鍵の取得も同じ呼び出しの中**で行う。

        ⚠ **鍵の取得を呼び手の try の外へ出さない。** JWT として壊れた入力は鍵を引く
        時点で ``jwt.DecodeError`` になる。外に出すと検証の網から漏れて 500 になる
        （未認証の相手が ``Bearer ごみ`` を投げるだけで起こせる）。
        """
        key = self._metadata.signing_key(metadata.jwks_uri, token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=list(metadata.signing_algorithms),
            # 発行者は discovery 文書のもの（引きに行った先と一致することは
            # OidcMetadataCache が確かめている）
            issuer=metadata.issuer,
            **options,
        )
        return claims

    def _verify(self, metadata: ProviderMetadata, exchange: CodeExchange, id_token: str) -> dict[str, Any]:
        """署名・発行者・対象者・``nonce`` を確かめる。

        ``nonce`` の照合を落とすと、別の場面で取った ID トークンを持ち込む
        （リプレイ）攻撃を止められない。
        """
        try:
            claims = self._decode(metadata, id_token, audience=exchange.provider.client_id)
        except jwt.InvalidTokenError as error:
            logger.warning("sso_id_token_rejected")
            raise InvalidIdTokenError from error
        if claims.get("nonce") != exchange.nonce:
            logger.warning("sso_id_token_nonce_mismatch")
            raise InvalidIdTokenError
        return claims

    def _userinfo(self, metadata: ProviderMetadata, access_token: str, claims: Mapping[str, Any]) -> dict[str, Any]:
        """UserInfo を引いて補う。取れなくてもログインは続ける。

        **``sub`` が食い違う応答は捨てる**（別人の情報で上書きされないように）。
        """
        try:
            document = self._get_json(metadata.userinfo_endpoint, access_token)
        except IdentityProviderUnavailableError:
            logger.warning("sso_userinfo_unavailable")
            return {}
        return document if document.get("sub") == claims.get("sub") else {}

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _post_form(self, url: str, form: Mapping[str, str], auth: tuple[str, str] | None) -> dict[str, Any]:
        try:
            response = httpx.post(
                url,
                data=dict(form),
                auth=auth,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
            return _as_document(response.json())
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("sso_token_request_failed")
            raise IdentityProviderUnavailableError from error

    def _get_json(self, url: str, access_token: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
            return _as_document(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise IdentityProviderUnavailableError from error


def _assertion_fields(provider: IdentityProvider, token_endpoint: str) -> dict[str, str]:
    """``private_key_jwt`` でトークン要求に足す 2 つの値。

    ``aud`` はトークンエンドポイントの URL。idp は ``<issuer>/token`` と
    ``<issuer>`` の両方を受けるが、discovery から得た値をそのまま使うほうが
    食い違わない。
    """
    assertion = build_client_assertion(
        ClientAssertionRequest(
            client_id=provider.client_id,
            audience=token_endpoint,
            credential=provider.credential,
        )
    )
    return {"client_assertion_type": ASSERTION_TYPE, "client_assertion": assertion}


def _as_document(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise IdentityProviderUnavailableError
    return payload


__all__ = ["HttpxOidcProviderGateway"]
