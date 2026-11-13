"""Token presented when calling assay's **admin API** (ADR-0077 §7).

Obtained via ``client_credentials`` + ``private_key_jwt``. Separate from the login registration (``OIDC_CLIENT_ID``),
it identifies as **this app's service account** (``MACHINE_CLIENT_ID``).

- **The audience is ``{issuer}/admin``.** Admin API tokens only pass with this ``aud``
  (idp ADR-0037). ⚠ **Not a setting** — it is derived from the issuer, not chosen by operators.
- **The method is always ``private_key_jwt``.** Even if login uses ``client_secret_basic``, machines hold no secret.
  The key is the same ``OIDC_PRIVATE_KEY_FILE`` / ``OIDC_PRIVATE_KEY_KID`` as login (ADR-0077 §1).

⚠ **assay must bind this service account as the app's identity.** Until then,
the admin API keeps returning 403 (the token itself can be obtained).
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

#: How many seconds before expiry to refetch. **Never 0** (expiring mid-request fails with 401).
_RENEW_MARGIN_SECONDS = 60.0

#: Lifetime (seconds) assumed when the expiry can't be read. ⚠ Reading it as unlimited would never refetch.
_FALLBACK_LIFETIME_SECONDS = 60.0

_REQUEST_TIMEOUT_SECONDS = 10.0


def admin_audience(issuer: str) -> str:
    """Audience stamped on admin API tokens.

    ⚠ **``issuer`` includes the tenant** (``https://identity.example/<tenant>``), so the
    audience is that plus ``/admin`` (idp ADR-0037).
    """
    return f"{issuer.rstrip('/')}/admin"


class AdminToken(Protocol):
    """Something that issues one token for the admin API.

    These two are all the roster side needs. **Depending on this shape rather than the class**
    lets tests swap it without running idp.
    """

    def token(self) -> str: ...

    def invalidate(self) -> None: ...


class AssayAdminTokenSource:
    """Obtain a token for the admin API and reuse it until it expires.

    One per process. Refetching every cycle would add one round trip to idp per reconciliation.
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
        """Discard the held token (called on receiving 401)."""
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
            # ⚠ The audience is **required** for the admin API. Omitting it yields a token without
            #   permissions, rejected by the admin API (idp ADR-0037).
            "resource": audience,
        }
        try:
            response = httpx.post(
                endpoint,
                data=form,
                # ⚠ Without identifying itself, Cloudflare in front of idp drops it.
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(
                f"the token endpoint is unreachable: {type(error).__name__}"
            ) from error
        if response.status_code != 200:
            # ⚠ Don't log the body as is (it may contain a token).
            logger.warning("assay_admin_token_failed", extra={"status_code": response.status_code})
            raise IdentityProviderUnavailableError(f"the token endpoint returned {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the token response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = ["AdminToken", "AssayAdminTokenSource", "admin_audience"]
