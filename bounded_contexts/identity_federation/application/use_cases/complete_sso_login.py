"""Completing SSO login (receive the return from the IdP and issue a redemption ticket).

Matches ``state`` against the round-trip state restored from the browser, exchanges the
authorization code for verified claims, resolves the user, then returns a short-lived
redemption ticket. Tokens themselves are not issued here (issued by Presentation's
:class:`TokenService`; exchanging the ticket for tokens is
:class:`~bounded_contexts.identity_federation.application.use_cases.exchange_sso_ticket.ExchangeSsoTicket`).

**The requested authentication strength is checked here.** Accepting an ID token that
doesn't meet the ``acr_values`` sent would make the request "sent only", and one typo in the
IdP-side policy would silently let single-factor logins through (ADR-0076 §3 decision 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from bounded_contexts.identity_federation.application.dto.sso_dto import SsoHandoffDto
from bounded_contexts.identity_federation.application.use_cases.resolve_federated_account import (
    ResolveFederatedAccount,
)
from bounded_contexts.identity_federation.domain.entities.sso_login_ticket import (
    SsoLoginTicket,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    SsoLoginTransactionInvalidError,
)
from bounded_contexts.identity_federation.domain.repositories.sso_login_ticket_repository import (
    SsoLoginTicketRepository,
)
from bounded_contexts.identity_federation.domain.services.login_secrets import (
    hash_secret,
    new_secret,
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
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
    require_usable,
)
from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class CompleteSsoLogin:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    tickets: SsoLoginTicketRepository
    claims: ClaimsMapping
    accounts: ResolveFederatedAccount
    ticket_ttl_seconds: int
    #: Matching the requested ``acr_values`` against the returned ``acr`` (ADR-0076 §3 decision 1).
    #: The default (nothing required) is built via :meth:`dataclasses.field`'s ``default_factory``
    #: — a value object placed as a default in the class body would be evaluated only once.
    requested_context: RequestedAuthenticationContext = field(default_factory=RequestedAuthenticationContext)

    def execute(
        self,
        *,
        code: str,
        state: str,
        transaction: LoginTransaction | None,
    ) -> SsoHandoffDto:
        provider = require_usable(self.provider)
        if transaction is None or not transaction.matches(state) or not transaction.is_for(provider.issuer):
            # Round-trip state can't be restored = not a return to the browser we sent out
            # (or the cookie was dropped / expired).
            raise SsoLoginTransactionInvalidError
        claims = self.gateway.exchange_code(
            CodeExchange(
                provider=provider,
                code=code,
                code_verifier=transaction.code_verifier,
                nonce=transaction.nonce,
            )
        )
        self.requested_context.ensure_satisfied(claims.get("acr"))
        federated_user = self.claims.apply(claims)
        account = self.accounts.execute(issuer=provider.issuer, user=federated_user)
        ticket = new_secret()
        started_at = utcnow()
        self.tickets.issue(
            SsoLoginTicket(
                ticket_hash=hash_secret(ticket),
                user_id=account.user_id,
                redirect_to=transaction.redirect_to,
                expires_at=started_at + timedelta(seconds=self.ticket_ttl_seconds),
                login=FederatedLogin(
                    session=_federated_session(provider.issuer, federated_user.subject, claims.get("sid")),
                    started_at=started_at,
                ),
            )
        )
        return SsoHandoffDto(ticket=ticket, redirect_to=transaction.redirect_to, account=account)


def _federated_session(issuer: str, subject: str, sid: object) -> FederatedSession:
    """Copy the ID token's ``sid`` into the address (ADR-0077 §3).

    Some IdPs don't provide ``sid``, so if absent proceed with ``None``
    (with that IdP sessions can be stopped **only per user**).
    """
    session_id = sid.strip() if isinstance(sid, str) else ""
    return FederatedSession(issuer=issuer, subject=subject, session_id=session_id or None)


__all__ = ["CompleteSsoLogin"]
