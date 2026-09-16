"""assay の**管理 API** を叩くときに名乗るトークン（ADR-0043）。

``client_credentials`` ＋ ``private_key_jwt`` で取る。ログイン用の登録（``OIDC_CLIENT_ID``）とは別の、
**このアプリのサービスアカウント**（``MACHINE_CLIENT_ID``）として名乗る。

- **宛名は ``{issuer}/admin``。** 管理 API のトークンはこの ``aud`` でなければ通らない
  （idp の ADR-0037）。⚠ **設定にしない** ——発行者から決まる値で、運用者が選ぶものではない。
- **方式は常に ``private_key_jwt``。** ログインが ``client_secret_basic`` でも、機械は秘密を持たない。
  鍵はログインと同じ ``OIDC_PRIVATE_KEY_FILE`` / ``OIDC_PRIVATE_KEY_KID`` を使う（ADR-0025）。

⚠ **assay 側でこのサービスアカウントをアプリの名乗りとして結び付ける必要がある。** 結び付けるまで、
管理 API は 403 を返し続ける（トークンそのものは取れる）。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

import httpx

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.value_objects.client_credential import (
    PRIVATE_KEY_JWT,
    ClientCredential,
)
from bounded_contexts.identity_federation.infrastructure.client_assertion import (
    ASSERTION_TYPE,
    ClientAssertionRequest,
    build_client_assertion,
)
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import (
    USER_AGENT,
    OidcMetadataCache,
)
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

#: 期限のどれだけ手前で取り直すか（秒）。**0 にしない**（送信中に期限が来ると 401 で落ちる）。
_RENEW_MARGIN_SECONDS = 60.0

#: 期限が読めなかったときに仮定する寿命（秒）。⚠ 無期限と読むと二度と取り直さない。
_FALLBACK_LIFETIME_SECONDS = 60.0

_REQUEST_TIMEOUT_SECONDS = 10.0


def admin_audience(issuer: str) -> str:
    """管理 API のトークンに刻む宛名。

    ⚠ **``issuer`` にはテナントが含まれる**（``https://identity.example/<tenant>``）ので、
    宛名はその後ろに ``/admin`` を足したものになる（idp の ADR-0037）。
    """
    return f"{issuer.rstrip('/')}/admin"


class AdminToken(Protocol):
    """管理 API 向けの 1 本を出すもの。

    名簿を引く側が要るのはこの 2 つだけ。**クラスではなくこの形に依存させる**ので、
    試験は idp を立てずに差し替えられる。
    """

    def token(self) -> str: ...

    def invalidate(self) -> None: ...


class AssayAdminTokenSource:
    """管理 API 用のトークンを取得し、期限まで使い回す。

    プロセスで 1 つ持つ。周回のたびに取り直すと、照合 1 回につき idp への往復が 1 つ増える。
    """

    def __init__(self, metadata: OidcMetadataCache | None = None) -> None:
        self._metadata = metadata or OidcMetadataCache()
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            issued, lifetime = self._request()
            self._token = issued
            self._expires_at = time.monotonic() + max(lifetime - _RENEW_MARGIN_SECONDS, 1.0)
            return self._token

    def invalidate(self) -> None:
        """控えているトークンを捨てる（401 を受けたときに呼ぶ）。"""
        with self._lock:
            self._token = ""
            self._expires_at = 0.0

    def _request(self) -> tuple[str, float]:
        client_id = settings.machine_client_id
        issuer = settings.oidc_issuer
        if not client_id or not issuer:
            raise SsoNotConfiguredError("MACHINE_CLIENT_ID / OIDC_ISSUER is not configured")
        endpoint = self._metadata.metadata(issuer).token_endpoint
        assertion = build_client_assertion(
            ClientAssertionRequest(
                client_id=client_id,
                audience=endpoint,
                credential=ClientCredential(
                    method=PRIVATE_KEY_JWT,
                    private_key_file=settings.oidc_private_key_file,
                    private_key_kid=settings.oidc_private_key_kid,
                ),
            )
        )
        payload = self._post(endpoint, client_id=client_id, assertion=assertion, audience=admin_audience(issuer))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise IdentityProviderUnavailableError("the token response has no access_token")
        lifetime = payload.get("expires_in")
        return token, float(lifetime) if isinstance(lifetime, (int, float)) else _FALLBACK_LIFETIME_SECONDS

    @staticmethod
    def _post(endpoint: str, *, client_id: str, assertion: str, audience: str) -> dict[str, object]:
        form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_assertion_type": ASSERTION_TYPE,
            "client_assertion": assertion,
            # ⚠ 管理 API では宛名が**必須**。省くと権限の載らないトークンになり、
            #   管理 API 側で弾かれる（idp の ADR-0037）。
            "resource": audience,
        }
        try:
            response = httpx.post(
                endpoint,
                data=form,
                # ⚠ 名乗らないと idp の前段の Cloudflare に落とされる。
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(
                f"the token endpoint is unreachable: {type(error).__name__}"
            ) from error
        if response.status_code != 200:
            # ⚠ 本文をそのままログに出さない（トークンが載りうる）。
            logger.warning("assay_admin_token_failed", extra={"status_code": response.status_code})
            raise IdentityProviderUnavailableError(f"the token endpoint returned {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the token response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = ["AdminToken", "AssayAdminTokenSource", "admin_audience"]
