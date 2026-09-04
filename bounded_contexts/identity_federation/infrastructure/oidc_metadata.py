"""OpenID Provider のメタデータ（エンドポイントと署名鍵）の取得とキャッシュ。

- **エンドポイントは discovery で引く**（``<issuer>/.well-known/openid-configuration``）。
  URL を 1 つずつ設定させると IdP 側の変更に追随できず、設定項目も増える。
- **署名鍵は JWKS から引く**。鍵は入れ替わるため、こちらも都度取りに行ける形で
  持つ（``PyJWKClient`` が内部でキャッシュと再取得を行う）。
- **外へ出る要求は名前を名乗る**（``USER_AGENT``）。既定のままだと IdP の前段に
  落とされることがある（下記）。

どちらもログインのたびに取りに行くと IdP への往復が 2 回増えるので、短い TTL の
キャッシュを挟む。プロセスごとのキャッシュで、値が古くなっても TTL のあいだだけ。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
)
from shared.kernel.version import load_build_info, project_name

# 受け入れる ID トークンの署名アルゴリズム。**対称鍵（HS*）と ``none`` は入れない**
# ——クライアントシークレットを鍵に使う HS* は IdP 以外も署名を作れてしまう。
ALLOWED_SIGNING_ALGORITHMS: tuple[str, ...] = (
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
)

_DISCOVERY_PATH = "/.well-known/openid-configuration"
_CACHE_TTL_SECONDS = 300.0

# 手元の鍵に無い ``kid`` が来たとき、JWKS を取り直してよい間隔（発行者ごと）。
# 短くしてあるのは、鍵の入れ替え直後に**新しい鍵を拒み続けない**ため。
_JWKS_REFRESH_INTERVAL_SECONDS = 60.0

# IdP へ出ていく要求が名乗る名前。**既定の UA に任せない。**
# JWKS だけは PyJWT (``PyJWKClient``) が内部の urllib で取りに行くため、既定では
# ``Python-urllib/3.x`` を名乗る。IdP の前段に居る CDN・WAF はこの UA を落とすことが
# あり（実際に Cloudflare が 403 を返し、ログインの折り返しだけが失敗した）、
# discovery とトークン交換は通るのに ID トークンの検証だけが落ちる形になる。
#
# ⚠ **名前を直に書かない。** アプリ自身の名前（``pyproject.toml`` の
# ``[project].name``）から導く（ADR-0031）。直に書くと、テンプレートから起こした
# アプリが**別のアプリの名前で名乗り続ける**——実際に長らくそうなっていた。
USER_AGENT = f"{project_name()}/{load_build_info().version}"


@dataclass(frozen=True)
class ProviderMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str = ""
    signing_algorithms: tuple[str, ...] = ()
    token_auth_methods: tuple[str, ...] = ()

    @classmethod
    def of(cls, document: dict[str, Any]) -> ProviderMetadata:
        """discovery 文書から必要な項目だけを取り出す。

        認可・トークン・JWKS のどれかが欠けている応答は OpenID Provider として
        成立していない（IdP の URL の書き間違いで HTML が返る場合もここで落ちる）。
        """
        metadata = cls(
            issuer=_text(document.get("issuer")),
            authorization_endpoint=_text(document.get("authorization_endpoint")),
            token_endpoint=_text(document.get("token_endpoint")),
            jwks_uri=_text(document.get("jwks_uri")),
            userinfo_endpoint=_text(document.get("userinfo_endpoint")),
            signing_algorithms=_supported_algorithms(document.get("id_token_signing_alg_values_supported")),
            token_auth_methods=tuple(_texts(document.get("token_endpoint_auth_methods_supported"))),
        )
        if not (metadata.authorization_endpoint and metadata.token_endpoint and metadata.jwks_uri):
            raise IdentityProviderUnavailableError
        return metadata


class OidcMetadataCache:
    """discovery 文書と JWKS クライアントの TTL キャッシュ（プロセス内）。"""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._documents: dict[str, tuple[float, ProviderMetadata]] = {}
        self._jwks: dict[str, jwt.PyJWKClient] = {}
        #: jwks_uri -> 最後に JWKS を取り直した時刻。下の ``signing_key`` を参照。
        self._jwks_refreshed_at: dict[str, float] = {}

    def metadata(self, issuer: str) -> ProviderMetadata:
        with self._lock:
            cached = self._documents.get(issuer)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
        metadata = ProviderMetadata.of(self._fetch(f"{issuer.rstrip('/')}{_DISCOVERY_PATH}"))
        _require_same_issuer(metadata, issuer)
        with self._lock:
            self._documents[issuer] = (time.monotonic() + _CACHE_TTL_SECONDS, metadata)
        return metadata

    def signing_key(self, jwks_uri: str, token: str) -> Any:
        """トークンの ``kid`` に対応する公開鍵を返す。

        ⚠ **呼ぶのは ``jwt.InvalidTokenError`` を捕まえる try の中から。** JWT として
        壊れた入力はここで ``jwt.DecodeError`` になる。外で呼ぶと、その例外が
        検証の網から漏れて 500 に化ける（``Bearer ごみ`` を投げるだけで起こせる）。

        ⚠ **JWKS の取り直しは発行者ごとに間隔を空ける。** ``PyJWKClient`` に任せると
        ``kid`` が見つからないたびに取り直す。機械の口（ADR-0060）は未認証の相手が
        **好きな ``kid`` のトークンを投げ込める**場所なので、「1 要求 = idp への 1 往復」に
        なり増幅の踏み台になる。``kid`` ごとに覚える形にしないのは、``kid`` を変え続ける
        相手には効かない（覚え書きも埋められる）ため。取り直しの回数を**発行者ごとに**
        抑えれば、``kid`` が何種類来ても往復は間隔あたり 1 回で済む。

        ⚠ **鍵が無いことと、JWKS が使えないことを分ける。** 前者はトークンが違う
        （呼び手が 401 にする）、後者は上流の不調（502）——届かないだけでなく、
        JSON でない・鍵が 1 本も無い・読めない鍵が入っている、も後者に入れる。
        トークンの誤りに見せると、正しい呼び出し元が自分の資格情報を疑う。
        """
        kid = _unverified_kid(token)
        if kid is None:
            # ``PyJWKClient`` は ``kid`` を持つ鍵しか候補にしないので、``kid`` の無い
            # トークンはどのみち照合できない。取りに行かずに断る。
            raise jwt.DecodeError("token has no kid")
        client = self._jwks_client(jwks_uri)
        try:
            key = jwt.PyJWKClient.match_kid(client.get_signing_keys(), kid)
            if key is None and self._may_refresh(jwks_uri):
                key = jwt.PyJWKClient.match_kid(client.get_signing_keys(refresh=True), kid)
        except (jwt.PyJWTError, ValueError) as error:
            # 届かない（``PyJWKClientConnectionError``）も、届いたが使えない
            # （``PyJWKClientError`` / ``PyJWKSetError`` / JSON でない）も上流の不調。
            raise IdentityProviderUnavailableError from error
        if key is None:
            raise jwt.DecodeError(f"no signing key for kid {kid}")
        return key.key

    def _jwks_client(self, jwks_uri: str) -> jwt.PyJWKClient:
        with self._lock:
            client = self._jwks.get(jwks_uri)
            if client is None:
                client = self._new_jwks_client(jwks_uri)
                self._jwks[jwks_uri] = client
        return client

    def _new_jwks_client(self, jwks_uri: str) -> jwt.PyJWKClient:
        try:
            return jwt.PyJWKClient(
                jwks_uri,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
        except jwt.PyJWKClientError as error:
            # discovery 文書が http(s) でない ``jwks_uri`` を名乗っている（IdP 側の不良）。
            raise IdentityProviderUnavailableError from error

    def _may_refresh(self, jwks_uri: str) -> bool:
        """取り直してよければ枠を取って真を返す（取りに行く前に取るので、同時に来た要求が重ならない）。"""
        with self._lock:
            now = time.monotonic()
            last = self._jwks_refreshed_at.get(jwks_uri)
            if last is not None and now - last < _JWKS_REFRESH_INTERVAL_SECONDS:
                return False
            self._jwks_refreshed_at[jwks_uri] = now
            return True

    def _fetch(self, url: str) -> dict[str, Any]:
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise IdentityProviderUnavailableError from error
        if not isinstance(document, dict):
            raise IdentityProviderUnavailableError
        return document


def _unverified_kid(token: str) -> str | None:
    """署名を検証せずヘッダーの ``kid`` だけを読む。無い・文字列でないなら ``None``。"""
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    return kid if isinstance(kid, str) and kid else None


def _require_same_issuer(metadata: ProviderMetadata, issuer: str) -> None:
    """discovery 文書が名乗る ``issuer`` が、引きに行った先と同じことを確かめる。

    OpenID Connect Discovery は両者の一致を要求している。取得は転送を追う
    （``follow_redirects``）ため、確かめないと別の発行者の文書を掴まされたときに
    その発行者が署名した ID トークンをそのまま受け入れてしまう。
    末尾の ``/`` の有無だけは許す（設定側で落としているため）。
    """
    if metadata.issuer.rstrip("/") != issuer.rstrip("/"):
        raise IdentityProviderUnavailableError


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_text(item) for item in value if _text(item))


def _supported_algorithms(value: object) -> tuple[str, ...]:
    """IdP が名乗ったアルゴリズムのうち、こちらが受け入れるものだけを残す。

    名乗りが無ければ OpenID Connect の必須である ``RS256`` を使う。
    """
    advertised = _texts(value)
    allowed = tuple(algorithm for algorithm in advertised if algorithm in ALLOWED_SIGNING_ALGORITHMS)
    return allowed or ("RS256",)


__all__ = ["ALLOWED_SIGNING_ALGORITHMS", "OidcMetadataCache", "ProviderMetadata"]
