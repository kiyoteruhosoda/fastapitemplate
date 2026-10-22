"""ユースケースの組み立て（``Depends()`` 用のファクトリ）。

設定（``settings`` の ``OIDC_*``）から値オブジェクトを起こすのはここだけ。
ユースケースは組み立て済みの :class:`IdentityProvider` などを受け取る。

**連携先はテナントごと**（ADR-0061・ADR-0064）。発行者とクライアント ID はテナントの行
（``tenants``）から、ほかの設定（クライアントの鍵・戻り先・要求する強度など）はアプリ全体の
設定から取る。どのテナントかは経路ごとに決まり方が違う:

- 入口（``/login``・``/provider``・``/logout``）: URL の ``?tenant=<slug>``。無ければ、テナントが
  1 つだけの環境ではそれ
- 戻り（``/callback``）: 送り出したときに往復状態へ書いた発行者（URL から決め直さない）
- 連携: 入っている利用者のテナント
- 停止の通知・アプリのトークン: トークンの発行者

IdP のメタデータ（discovery・JWKS）はプロセス内でキャッシュするため、ゲートウェイは
**1 つを使い回す**。テストは ``app.dependency_overrides[dependencies.oidc_gateway]``
で差し替える。
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
    """トークンエンドポイントへ名乗る手段を設定から起こす（ADR-0025）。"""
    return ClientCredential(
        method=settings.oidc_client_auth_method,
        secret=settings.oidc_client_secret,
        private_key_file=settings.oidc_private_key_file,
        private_key_kid=settings.oidc_private_key_kid,
    )


def identity_provider(tenant: Tenant | None) -> IdentityProvider | None:
    """テナントの連携先を起こす。SSO が無効・テナントが無い・止めた・SSO を持たないなら ``None``。"""
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
    """発行者のテナントの連携先。登録の無い発行者なら ``None``。"""
    return identity_provider(tenant_issuing(db, issuer))


def provider_of(db: Session, user: User) -> IdentityProvider | None:
    """利用者のテナントの連携先（連携の往復は、入っている人のテナントで行う）。"""
    return identity_provider(db.get(Tenant, user.tenant_id) if user.tenant_id is not None else None)


def entrance(
    db: DbDep,
    tenant: Annotated[str | None, Query(max_length=50, pattern=r"^[a-z0-9-]+$")] = None,
) -> Tenant | None:
    """入口で選ばれたテナント（``?tenant=<slug>``。ADR-0061 決定 8）。"""
    return entrance_tenant(db, tenant)


EntranceDep = Annotated[Tenant | None, Depends(entrance)]
SignedInUserDep = Annotated[User, Depends(get_current_user)]


def claims_mapping() -> ClaimsMapping:
    return ClaimsMapping(
        email_claim=settings.oidc_email_claim,
        username_claim=settings.oidc_username_claim,
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
        settings.oidc_default_roles,
        sync_on_login=settings.oidc_role_sync,
    )


def describe_sso_provider(tenant: EntranceDep) -> DescribeSsoProvider:
    return DescribeSsoProvider(
        provider=identity_provider(tenant),
        rp_logout_enabled=settings.oidc_rp_logout_enabled,
    )


def requested_authentication_context() -> RequestedAuthenticationContext:
    """要求する認証の強度（ADR-0026 決定 1）。空 = 要求しない。"""
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
    """連携の往復の開始（ADR-0040）。要求する認証の強度はログインと同じ。"""
    return StartSsoLink(
        provider=provider_of(db, user),
        gateway=gateway,
        acr_values=tuple(settings.oidc_acr_values),
    )


@dataclass(frozen=True)
class SsoCompletion:
    """IdP からの戻りの後始末。**どの連携先で受けるかは往復状態の発行者で決まる**ので、
    戻りを読んでから組み立てる。"""

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
    """発行者のテナントの利用者を決める（寄せる・作るのも、そのテナントの中だけ）。"""
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
    """停止の伝播の受け口（ADR-0036）。連携先は通知の発行者のテナントで決まる。

    記録を残す期間は**リフレッシュトークンの寿命**に合わせる。これを過ぎれば
    停止より前に発行されたトークンは自力で期限切れになる。
    """

    db: Session
    gateway: OidcProviderGateway

    def from_issuer(self, issuer: str) -> ReceiveBackchannelLogout:
        return ReceiveBackchannelLogout(
            provider=provider_issuing(self.db, issuer),
            gateway=self.gateway,
            revocations=SqlSessionRevocationRepository(self.db),
            keep_for_seconds=settings.refresh_token_expires_seconds,
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
