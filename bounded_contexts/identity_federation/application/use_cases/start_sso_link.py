"""Starting a link — begin the IdP round trip for **an already signed-in user** (ADR-0077 §5).

The only difference from a login round trip is the round-trip state; the authorization request
sent to the IdP is the same (only one redirect URI is registered). The round-trip state holds

- ``purpose = LINK`` — marker of which follow-up to run on return
- ``user_id`` — **the person who started it**

⚠ **Putting ``user_id`` in is the crux of this round trip.** Without it, a browser whose
user switched mid-round-trip would bind **to someone else's account** on return.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import (
    SsoAuthorizationDto,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_login import (
    authorization_for,
)
from bounded_contexts.identity_federation.domain.services.login_secrets import (
    new_code_verifier,
    new_secret,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
    require_usable,
)
from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)


@dataclass(frozen=True)
class StartSsoLink:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    #: ``acr_values`` to put in the authorization request (empty = none required). ADR-0076 §3 decision 1.
    acr_values: tuple[str, ...] = ()

    def execute(self, *, user_id: int) -> SsoAuthorizationDto:
        provider = require_usable(self.provider)
        transaction = LoginTransaction(
            state=new_secret(),
            nonce=new_secret(),
            code_verifier=new_code_verifier(),
            issuer=provider.issuer,
            purpose=TransactionPurpose.LINK,
            user_id=user_id,
        )
        return authorization_for(provider, self.gateway, transaction, self.acr_values)


__all__ = ["StartSsoLink"]
