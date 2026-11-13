"""Use case wiring (factories for ``Depends()``).

This is the only place that builds value objects from settings (``OIDC_*`` in ``settings``).
Use cases receive already-built objects such as :class:`IdentityProvider`.

**The connection is per tenant** (ADR-0079 §1, §4). Issuer and client ID come from the
tenant row (``tenants``); other settings (client key, redirect URI, required strength, etc.)
come from app-wide settings.
Which tenant is determined differently per route:

- Entrance (``/login``, ``/provider``, ``/logout``): ``?tenant=<slug>`` in the URL. If absent,
  the only tenant in single-tenant environments
- Return (``/callback``): the issuer written into the round-trip state when sending out
  (not re-derived from the URL)
- Linking: the signed-in user's tenant
- Logout notices / app tokens: the token's issuer

IdP metadata (discovery, JWKS) is cached in-process, so **a single gateway is reused**.
Tests replace it via ``app.dependency_overrides[dependencies.oidc_gateway]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.application.use_cases.build_rp_logout_url import (
    BuildRpLogoutUrl,
)
from bounded_contexts.identity_federation.application.use_cases.complete_sso_link import (
    CompleteSsoLink,
)
from bounded_contexts.identity_federation.application.use_cases.complete_sso_login import (
    CompleteSsoLogin,
)
from bounded_contexts.identity_federation.application.use_cases.describe_federated_link import (
    DescribeFederatedLink,
)
from bounded_contexts.identity_federation.application.use_cases.describe_sso_provider import (
    DescribeSsoProvider,
)
from bounded_contexts.identity_federation.application.use_cases.exchange_sso_ticket import (
    ExchangeSsoTicket,
)
from bounded_contexts.identity_federation.application.use_cases.receive_backchannel_logout import (
    ReceiveBackchannelLogout,
)
from bounded_contexts.identity_federation.application.use_cases.resolve_federated_account import (
    ResolveFederatedAccount,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_link import (
    StartSsoLink,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_login import (
    StartSsoLogin,
)
from bounded_contexts.identity_federation.application.use_cases.unlink_federated_identity import (
    UnlinkFederatedIdentity,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.account_linking_policy import (
    AccountLinkingPolicy,
)
from bounded_contexts.identity_federation.domain.value_objects.authentication_context import (
    RequestedAuthenticationContext,
)
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import (
    ClaimsMapping,
)
from bounded_contexts.identity_federation.domain.value_objects.client_credential import (
    ClientCredential,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)
from bounded_contexts.identity_federation.domain.value_objects.provisioning_policy import (
    ProvisioningPolicy,
)
from bounded_contexts.identity_federation.domain.value_objects.role_assignment import (
    RoleAssignment,
)
from bounded_contexts.identity_federation.infrastructure.httpx_oidc_provider_gateway import (
    HttpxOidcProviderGateway,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_user_directory import (
    SqlFederatedUserDirectory,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from bounded_contexts.identity_federation.infrastructure.sql_sso_login_ticket_repository import (
    SqlSsoLoginTicketRepository,
)
from presentation.fastapi.dependencies.auth import get_current_user
from shared.infrastructure.models import Tenant, User
from shared.infrastructure.tenant_directory import entrance_tenant, tenant_issuing, tenant_of_issuer
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

DbDep = Annotated[Session, Depends(get_db)]

_gateway = HttpxOidcProviderGateway()


def oidc_gateway() -> OidcProviderGateway:
    return _gateway


GatewayDep = Annotated[OidcProviderGateway, Depends(oidc_gateway)]


def client_credential() -> ClientCredential:
    """Build from settings the means of authenticating to the token endpoint (ADR-0077 §1)."""
    return ClientCredential(
        method=settings.oidc_client_auth_method,
        secret=settings.oidc_client_secret,
        private_key_file=settings.oidc_private_key_file,
        private_key_kid=settings.oidc_private_key_kid,
    )


def identity_provider(tenant: Tenant | None) -> IdentityProvider | None:
    """Build the tenant's connection. ``None`` if SSO is disabled, or the tenant is missing,
    suspended, or has no SSO."""
    if not settings.oidc_enabled or tenant is None or not tenant.is_active:
        return None
    if not tenant.issuer or not tenant.client_id:
        return None
    return IdentityProvider(
        display_name=settings.oidc_display_name,
        issuer=tenant.issuer,
        client_id=tenant.client_id,
        credential=client_credential(),
        redirect_uri=settings.oidc_redirect_uri,
        scopes=tuple(settings.oidc_scopes),
    )


def provider_issuing(db: Session, issuer: str) -> IdentityProvider | None:
    """The connection of the issuer's tenant. ``None`` for an unregistered issuer."""
    return identity_provider(tenant_issuing(db, issuer))


def provider_of(db: Session, user: User) -> IdentityProvider | None:
    """The connection of the user's tenant (linking runs in the signed-in user's tenant)."""
    return identity_provider(db.get(Tenant, user.tenant_id) if user.tenant_id is not None else None)


def entrance(
    db: DbDep,
    tenant: Annotated[str | None, Query(max_length=50, pattern=r"^[a-z0-9-]+$")] = None,
) -> Tenant | None:
    """Tenant chosen at the entrance (``?tenant=<slug>``. ADR-0079 §1 decision 8)."""
    return entrance_tenant(db, tenant)


EntranceDep = Annotated[Tenant | None, Depends(entrance)]
SignedInUserDep = Annotated[User, Depends(get_current_user)]


def claims_mapping() -> ClaimsMapping:
    return ClaimsMapping(
        email_claim=settings.oidc_email_claim,
        username_claim=settings.oidc_username_claim,
    )


def account_linking_policy() -> AccountLinkingPolicy:
    """Whether to accept the party / whether to merge into an existing user (ADR-0077 §1 decision 4)."""
    return AccountLinkingPolicy(
        link_by_email=settings.oidc_link_by_email,
        allowed_email_domains=tuple(settings.oidc_allowed_email_domains),
    )


def provisioning_policy() -> ProvisioningPolicy:
    return ProvisioningPolicy(auto_provision=settings.oidc_auto_provision)


def role_assignment() -> RoleAssignment:
    return RoleAssignment.from_rules(
        settings.oidc_default_roles,
        sync_on_login=settings.oidc_role_sync,
    )


def describe_sso_provider(tenant: EntranceDep) -> DescribeSsoProvider:
    return DescribeSsoProvider(
        provider=identity_provider(tenant),
        rp_logout_enabled=settings.oidc_rp_logout_enabled,
    )


def requested_authentication_context() -> RequestedAuthenticationContext:
    """Required authentication strength (ADR-0076 §3 decision 1). Empty = none required."""
    return RequestedAuthenticationContext(values=tuple(settings.oidc_acr_values))


def build_rp_logout_url(gateway: GatewayDep, tenant: EntranceDep) -> BuildRpLogoutUrl:
    return BuildRpLogoutUrl(
        provider=identity_provider(tenant),
        gateway=gateway,
        enabled=settings.oidc_rp_logout_enabled,
        post_logout_redirect_uri=settings.oidc_post_logout_redirect_uri,
    )


def start_sso_login(gateway: GatewayDep, tenant: EntranceDep) -> StartSsoLogin:
    return StartSsoLogin(
        provider=identity_provider(tenant),
        gateway=gateway,
        acr_values=tuple(settings.oidc_acr_values),
    )


def start_sso_link(gateway: GatewayDep, db: DbDep, user: SignedInUserDep) -> StartSsoLink:
    """Start of the linking round trip (ADR-0077 §5). Required strength is the same as for login."""
    return StartSsoLink(
        provider=provider_of(db, user),
        gateway=gateway,
        acr_values=tuple(settings.oidc_acr_values),
    )


@dataclass(frozen=True)
class SsoCompletion:
    """Follow-up of the IdP return. **The connection is decided by the issuer in the round-trip
    state**, so it is built after reading the return."""

    db: Session
    gateway: OidcProviderGateway

    def login(self, issuer: str) -> CompleteSsoLogin:
        return CompleteSsoLogin(
            provider=provider_issuing(self.db, issuer),
            gateway=self.gateway,
            tickets=SqlSsoLoginTicketRepository(self.db),
            claims=claims_mapping(),
            accounts=resolve_federated_account(self.db, issuer),
            ticket_ttl_seconds=settings.oidc_login_ticket_ttl_seconds,
            requested_context=requested_authentication_context(),
        )

    def link(self, issuer: str) -> CompleteSsoLink:
        return CompleteSsoLink(
            provider=provider_issuing(self.db, issuer),
            gateway=self.gateway,
            identities=SqlFederatedIdentityRepository(self.db),
            claims=claims_mapping(),
            requested_context=requested_authentication_context(),
        )


def sso_completion(db: DbDep, gateway: GatewayDep) -> SsoCompletion:
    return SsoCompletion(db=db, gateway=gateway)


def describe_federated_link(db: DbDep, user: SignedInUserDep) -> DescribeFederatedLink:
    return DescribeFederatedLink(
        identities=SqlFederatedIdentityRepository(db),
        provider=provider_of(db, user),
    )


def unlink_federated_identity(db: DbDep) -> UnlinkFederatedIdentity:
    return UnlinkFederatedIdentity(identities=SqlFederatedIdentityRepository(db))


def resolve_federated_account(db: Session, issuer: str) -> ResolveFederatedAccount:
    """Resolve the user in the issuer's tenant (merging and creating happen only within that tenant)."""
    return ResolveFederatedAccount(
        identities=SqlFederatedIdentityRepository(db),
        directory=SqlFederatedUserDirectory(db, tenant_of_issuer(db, issuer)),
        linking=account_linking_policy(),
        policy=provisioning_policy(),
        roles=role_assignment(),
    )


def exchange_sso_ticket(db: DbDep) -> ExchangeSsoTicket:
    return ExchangeSsoTicket(tickets=SqlSsoLoginTicketRepository(db))


@dataclass(frozen=True)
class BackchannelLogout:
    """Receiver for logout propagation (ADR-0077 §3). The connection is the notice issuer's tenant.

    Records are kept for at least **the refresh token lifetime**. After that, tokens issued before
    the logout expire on their own (while old logins remain, see ADR-0102).
    SSO logins carry no refresh credential (ADR-0104), so it is never shorter than
    **the access token lifetime**.
    """

    db: Session
    gateway: OidcProviderGateway

    def from_issuer(self, issuer: str) -> ReceiveBackchannelLogout:
        return ReceiveBackchannelLogout(
            provider=provider_issuing(self.db, issuer),
            gateway=self.gateway,
            revocations=SqlSessionRevocationRepository(self.db),
            keep_for_seconds=max(settings.refresh_token_expires_seconds, settings.access_token_expires_seconds),
        )


def receive_backchannel_logout(db: DbDep, gateway: GatewayDep) -> BackchannelLogout:
    return BackchannelLogout(db=db, gateway=gateway)


__all__ = [
    "BackchannelLogout",
    "DbDep",
    "EntranceDep",
    "GatewayDep",
    "SsoCompletion",
    "account_linking_policy",
    "build_rp_logout_url",
    "claims_mapping",
    "client_credential",
    "describe_federated_link",
    "describe_sso_provider",
    "entrance",
    "exchange_sso_ticket",
    "identity_provider",
    "oidc_gateway",
    "provider_issuing",
    "provider_of",
    "provisioning_policy",
    "receive_backchannel_logout",
    "requested_authentication_context",
    "resolve_federated_account",
    "role_assignment",
    "sso_completion",
    "start_sso_link",
    "start_sso_login",
    "unlink_federated_identity",
]
