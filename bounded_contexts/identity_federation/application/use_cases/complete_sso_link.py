"""Completing a link — bind the returned ``(issuer, subject)`` to **the currently signed-in user**.

The difference from login completion (:class:`CompleteSsoLogin`) is that it **doesn't search**
for a user. Who to bind to was fixed when the round trip started; there's no room to re-decide
here (ADR-0077 §5).

Three refusal cases.

- Round-trip state can't be restored / ``state`` doesn't match — not a return to the browser we sent out
- The user who started the round trip differs from the current session — can't decide which to bind
- That ``(issuer, subject)`` is bound to **a different user** — it would be a takeover
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAlreadyLinkedError,
    SsoIdentityTakenError,
    SsoLinkSessionMismatchError,
    SsoLoginTransactionInvalidError,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    CodeExchange,
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.authentication_context import (
    RequestedAuthenticationContext,
)
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import (
    ClaimsMapping,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
    require_usable,
)
from bounded_contexts.identity_federation.domain.value_objects.sso_callback import (
    SsoCallback,
)


@dataclass(frozen=True)
class CompleteSsoLink:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    identities: FederatedIdentityRepository
    claims: ClaimsMapping
    #: Matching the requested ``acr_values`` against the returned ``acr`` (ADR-0076 §3 decision 1).
    requested_context: RequestedAuthenticationContext = field(default_factory=RequestedAuthenticationContext)

    def execute(self, *, callback: SsoCallback, user_id: int) -> FederatedIdentity:
        provider = require_usable(self.provider)
        transaction = callback.transaction
        if transaction is None or not transaction.matches(callback.state) or not transaction.is_for(provider.issuer):
            raise SsoLoginTransactionInvalidError
        if not transaction.belongs_to(user_id):
            # ⚠ Signed out mid-round-trip, or signed in again as another user. **Don't rebind to the
            #   current session** — a way in would sprout on an account other than the initiator's.
            raise SsoLinkSessionMismatchError
        claims = self.gateway.exchange_code(
            CodeExchange(
                provider=provider,
                code=callback.code,
                code_verifier=transaction.code_verifier,
                nonce=transaction.nonce,
            )
        )
        self.requested_context.ensure_satisfied(claims.get("acr"))
        subject = self.claims.apply(claims).subject
        self._ensure_free(provider.issuer, subject, user_id)
        return self.identities.link(FederatedIdentity(issuer=provider.issuer, subject=subject, user_id=user_id))

    def _ensure_free(self, issuer: str, subject: str, user_id: int) -> None:
        taken = self.identities.find(issuer, subject)
        if taken is not None and taken.user_id != user_id:
            raise SsoIdentityTakenError
        mine = self.identities.find_for_user(issuer, user_id)
        if mine is not None and mine.subject != subject:
            # Replacement is not silently allowed: the path that signed in via the previous binding
            # would vanish.
            raise SsoAlreadyLinkedError


__all__ = ["CompleteSsoLink"]
