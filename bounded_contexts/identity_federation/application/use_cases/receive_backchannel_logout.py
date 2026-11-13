"""Receive logout notices from the IdP (OpenID Connect Back-Channel Logout 1.0. ADR-0077 §3).

This endpoint is **not called from the user's browser**. It's a server-to-server path hit
directly by the IdP's server; the received ``logout_token``'s signature is the only proof of the sender.

It does just one thing — record "this session may no longer be used".
The session itself is a JWT with no server-side copy, so there's nothing to drop here
(validity is checked the next time the token is presented).
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    LogoutTokenVerification,
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
    require_usable,
)
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import (
    LogoutNotice,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class ReceiveBackchannelLogout:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    revocations: SessionRevocationRepository
    #: Minimum seconds to keep records. Pass **the refresh token lifetime** — past that, tokens
    #: issued before the record expire on their own, and the row serves no purpose.
    #: If old logins last longer after the period was shortened, it is extended on save (ADR-0102).
    keep_for_seconds: int

    def execute(self, *, logout_token: str) -> LogoutNotice:
        provider = require_usable(self.provider)
        claims = self.gateway.verify_logout_token(LogoutTokenVerification(provider=provider, logout_token=logout_token))
        notice = LogoutNotice.from_claims(claims, issuer=provider.issuer)
        self.revocations.record(SessionRevocation.of(notice, now=utcnow(), keep_for_seconds=self.keep_for_seconds))
        return notice


__all__ = ["ReceiveBackchannelLogout"]
