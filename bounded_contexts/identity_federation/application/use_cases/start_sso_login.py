"""Starting SSO login (building the authorization request).

Creates ``state`` / ``nonce`` / PKCE ``code_verifier`` here and returns the URL to the IdP's
authorization endpoint and the **round-trip state**. No server-side copy of the round-trip
state is kept; the caller (Presentation) entrusts it to the browser as a signed cookie
(ADR-0077 §1). No table and no cleanup needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import (
    ContinuedSessionDto,
    SsoAuthorizationDto,
)
from bounded_contexts.identity_federation.domain.services.login_secrets import (
    code_challenge_of,
    new_code_verifier,
    new_secret,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
    require_usable,
)
from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from bounded_contexts.identity_federation.domain.value_objects.redirect_target import (
    RedirectTarget,
)
from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)


@dataclass(frozen=True)
class StartSsoLogin:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    #: ``acr_values`` to put in the authorization request (empty = none required). ADR-0076 §3 decision 1.
    acr_values: tuple[str, ...] = ()

    def execute(self, *, redirect_to: str | None = None, silent: bool = False) -> SsoAuthorizationDto:
        """Return the URL to send to the IdP and the round-trip state to entrust to the browser.

        If ``silent``, the IdP is told not to show a screen (``prompt=none``. ADR-0077 §9).
        """
        provider = require_usable(self.provider)
        transaction = LoginTransaction(
            state=new_secret(),
            nonce=new_secret(),
            code_verifier=new_code_verifier(),
            issuer=provider.issuer,
            redirect_to=RedirectTarget.parse(redirect_to).path,
            silent=silent,
        )
        return authorization_for(provider, self.gateway, transaction, self.acr_values)

    def renew(self, continued: ContinuedSessionDto | None) -> SsoAuthorizationDto:
        """Round trip that silently continues an expired login (inside a hidden frame. ADR-0104).

        Always ``prompt=none``. ``continued`` is read from the leftover expired token; if the person
        who comes back is the same, the role and sign-in time are carried over. ``None`` if unreadable
        (then it signs in as a new login).
        """
        provider = require_usable(self.provider)
        transaction = LoginTransaction(
            state=new_secret(),
            nonce=new_secret(),
            code_verifier=new_code_verifier(),
            issuer=provider.issuer,
            purpose=TransactionPurpose.RENEW,
            silent=True,
            user_id=continued.user_id if continued is not None else None,
            active_role=continued.active_role if continued is not None else None,
            authenticated_at=continued.authenticated_at if continued is not None else None,
            signed_in_with_passkey=continued.signed_in_with_passkey if continued is not None else False,
        )
        return authorization_for(provider, self.gateway, transaction, self.acr_values)


def authorization_for(
    provider: IdentityProvider,
    gateway: OidcProviderGateway,
    transaction: LoginTransaction,
    acr_values: tuple[str, ...],
) -> SsoAuthorizationDto:
    """Build the authorization request URL from the round-trip state.

    It is **exactly the same** for login and linking round trips (ADR-0077 §5), so it lives in one place.
    Only the round-trip state contents (``purpose`` and ``user_id``) differ; what is sent to the IdP
    doesn't change — only one redirect URI is registered.
    """
    authorization_url = gateway.authorization_url(
        AuthorizationRequest(
            provider=provider,
            state=transaction.state,
            nonce=transaction.nonce,
            code_challenge=code_challenge_of(transaction.code_verifier),
            acr_values=acr_values,
            silent=transaction.silent,
        )
    )
    return SsoAuthorizationDto(authorization_url=authorization_url, transaction=transaction)


__all__ = ["StartSsoLogin", "authorization_for"]
