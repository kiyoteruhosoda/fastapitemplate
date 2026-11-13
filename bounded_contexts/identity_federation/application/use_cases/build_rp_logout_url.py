"""Build where to send the browser to carry sign-out through to the IdP (RP-Initiated Logout 1.0).

**Ending the app session is a separate job** (``POST /api/auth/logout``). This only decides
"where to send the browser afterwards", including the decision not to send it.

``None`` is returned in the 4 cases below. None are failures, so the caller should simply
return to an in-app destination (the login screen).

1. Disabled by settings (the default of ``OIDC_RP_LOGOUT_ENABLED``)
2. SSO itself is unavailable
3. The IdP doesn't publish ``end_session_endpoint``
4. discovery can't be fetched (IdP unreachable)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    EndSessionRequest,
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildRpLogoutUrl:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    enabled: bool = False
    #: Where the IdP returns to after sign-out. Omitted if empty.
    post_logout_redirect_uri: str = ""

    def execute(self) -> str | None:
        if not self.enabled:
            return None
        provider = self.provider
        if provider is None or not provider.is_usable:
            return None
        try:
            return self.gateway.end_session_url(
                EndSessionRequest(
                    provider=provider,
                    post_logout_redirect_uri=self.post_logout_redirect_uri,
                )
            )
        except IdentityProviderUnavailableError:
            # Don't refuse sign-out because discovery can't be fetched. The app-side session
            # has already ended, so it just **has no return destination**.
            logger.warning("sso_end_session_unavailable")
            return None


__all__ = ["BuildRpLogoutUrl"]
