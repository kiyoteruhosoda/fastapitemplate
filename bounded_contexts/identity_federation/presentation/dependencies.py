"""ユースケースの組み立て（``Depends()`` 用のファクトリ）。

設定（``settings`` の ``OIDC_*``）から値オブジェクトを起こすのはここだけ。
ユースケースは組み立て済みの :class:`IdentityProvider` などを受け取る。

IdP のメタデータ（discovery・JWKS）はプロセス内でキャッシュするため、ゲートウェイは
**1 つを使い回す**。テストは ``app.dependency_overrides[dependencies.oidc_gateway]``
で差し替える。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.application.use_cases.complete_sso_login import (
    CompleteSsoLogin,
)
from bounded_contexts.identity_federation.application.use_cases.describe_sso_provider import (
    DescribeSsoProvider,
)
from bounded_contexts.identity_federation.application.use_cases.exchange_sso_ticket import (
    ExchangeSsoTicket,
)
from bounded_contexts.identity_federation.application.use_cases.resolve_federated_account import (
    ResolveFederatedAccount,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_login import (
    StartSsoLogin,
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
from bounded_contexts.identity_federation.infrastructure.sql_sso_login_ticket_repository import (
    SqlSsoLoginTicketRepository,
)
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

DbDep = Annotated[Session, Depends(get_db)]

_gateway = HttpxOidcProviderGateway()


def oidc_gateway() -> OidcProviderGateway:
    return _gateway


GatewayDep = Annotated[OidcProviderGateway, Depends(oidc_gateway)]


def client_credential() -> ClientCredential:
    """トークンエンドポイントへ名乗る手段を設定から起こす（ADR-0025）。"""
    return ClientCredential(
        method=settings.oidc_client_auth_method,
        secret=settings.oidc_client_secret,
        private_key_file=settings.oidc_private_key_file,
        private_key_kid=settings.oidc_private_key_kid,
    )


def identity_provider() -> IdentityProvider | None:
    """設定から連携先を起こす。無効なら ``None``。"""
    if not settings.oidc_enabled:
        return None
    return IdentityProvider(
        display_name=settings.oidc_display_name,
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        credential=client_credential(),
        redirect_uri=settings.oidc_redirect_uri,
        scopes=tuple(settings.oidc_scopes),
    )


def claims_mapping() -> ClaimsMapping:
    return ClaimsMapping(
        email_claim=settings.oidc_email_claim,
        username_claim=settings.oidc_username_claim,
        groups_claim=settings.oidc_groups_claim,
    )


def account_linking_policy() -> AccountLinkingPolicy:
    """受け入れてよい相手か・既存の利用者へ寄せてよいか（ADR-0025 決定 4）。"""
    return AccountLinkingPolicy(
        link_by_email=settings.oidc_link_by_email,
        allowed_email_domains=tuple(settings.oidc_allowed_email_domains),
    )


def provisioning_policy() -> ProvisioningPolicy:
    return ProvisioningPolicy(auto_provision=settings.oidc_auto_provision)


def role_assignment() -> RoleAssignment:
    return RoleAssignment.from_rules(
        settings.oidc_role_mapping,
        settings.oidc_default_roles,
        sync_on_login=settings.oidc_role_sync,
    )


def describe_sso_provider() -> DescribeSsoProvider:
    return DescribeSsoProvider(provider=identity_provider())


def requested_authentication_context() -> RequestedAuthenticationContext:
    """要求する認証の強度（ADR-0026 決定 1）。空 = 要求しない。"""
    return RequestedAuthenticationContext(values=tuple(settings.oidc_acr_values))


def start_sso_login(gateway: GatewayDep) -> StartSsoLogin:
    return StartSsoLogin(
        provider=identity_provider(),
        gateway=gateway,
        acr_values=tuple(settings.oidc_acr_values),
    )


def resolve_federated_account(db: DbDep) -> ResolveFederatedAccount:
    return ResolveFederatedAccount(
        identities=SqlFederatedIdentityRepository(db),
        directory=SqlFederatedUserDirectory(db),
        linking=account_linking_policy(),
        policy=provisioning_policy(),
        roles=role_assignment(),
    )


def complete_sso_login(db: DbDep, gateway: GatewayDep) -> CompleteSsoLogin:
    return CompleteSsoLogin(
        provider=identity_provider(),
        gateway=gateway,
        tickets=SqlSsoLoginTicketRepository(db),
        claims=claims_mapping(),
        accounts=resolve_federated_account(db),
        ticket_ttl_seconds=settings.oidc_login_ticket_ttl_seconds,
        requested_context=requested_authentication_context(),
    )


def exchange_sso_ticket(db: DbDep) -> ExchangeSsoTicket:
    return ExchangeSsoTicket(tickets=SqlSsoLoginTicketRepository(db))


__all__ = [
    "DbDep",
    "GatewayDep",
    "account_linking_policy",
    "claims_mapping",
    "client_credential",
    "complete_sso_login",
    "describe_sso_provider",
    "exchange_sso_ticket",
    "identity_provider",
    "oidc_gateway",
    "provisioning_policy",
    "requested_authentication_context",
    "resolve_federated_account",
    "role_assignment",
    "start_sso_login",
]
