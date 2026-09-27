"""SSO ログインの開始（認可要求の組み立て）。

``state`` / ``nonce`` / PKCE の ``code_verifier`` をここで作り、IdP の認可
エンドポイントへの URL と**往復状態**を返す。往復状態はサーバー側に控えを持たず、
呼び出し側（Presentation 層）が署名付き Cookie にしてブラウザへ預ける
（ADR-0025）。表も掃除も要らない。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import (
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


@dataclass(frozen=True)
class StartSsoLogin:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    #: 認可要求に載せる ``acr_values``（空 = 要求しない）。ADR-0026 決定 1。
    acr_values: tuple[str, ...] = ()

    def execute(self, *, redirect_to: str | None = None) -> SsoAuthorizationDto:
        """IdP へ送り出す URL と、ブラウザへ預ける往復状態を返す。"""
        provider = require_usable(self.provider)
        transaction = LoginTransaction(
            state=new_secret(),
            nonce=new_secret(),
            code_verifier=new_code_verifier(),
            redirect_to=RedirectTarget.parse(redirect_to).path,
        )
        return authorization_for(provider, self.gateway, transaction, self.acr_values)


def authorization_for(
    provider: IdentityProvider,
    gateway: OidcProviderGateway,
    transaction: LoginTransaction,
    acr_values: tuple[str, ...],
) -> SsoAuthorizationDto:
    """往復状態から認可要求の URL を組む。

    ログインの往復と連携の往復（ADR-0040）で**まったく同じ**なので 1 か所に置く。
    違うのは往復状態の中身（``purpose`` と ``user_id``）だけで、IdP へ送るものは
    変わらない ——戻り先の URI も 1 つしか登録しない。
    """
    authorization_url = gateway.authorization_url(
        AuthorizationRequest(
            provider=provider,
            state=transaction.state,
            nonce=transaction.nonce,
            code_challenge=code_challenge_of(transaction.code_verifier),
            acr_values=acr_values,
        )
    )
    return SsoAuthorizationDto(authorization_url=authorization_url, transaction=transaction)


__all__ = ["StartSsoLogin", "authorization_for"]
