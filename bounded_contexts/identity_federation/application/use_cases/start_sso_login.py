"""SSO ログインの開始（認可要求の組み立て）。

``state`` / ``nonce`` / PKCE の ``code_verifier`` をここで作り、IdP の認可
エンドポイントへの URL と**往復状態**を返す。往復状態はサーバー側に控えを持たず、
呼び出し側（Presentation 層）が署名付き Cookie にしてブラウザへ預ける
（ADR-0077 §1）。表も掃除も要らない。
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
    #: 認可要求に載せる ``acr_values``（空 = 要求しない）。ADR-0076 §3 決定 1。
    acr_values: tuple[str, ...] = ()

    def execute(self, *, redirect_to: str | None = None, silent: bool = False) -> SsoAuthorizationDto:
        """IdP へ送り出す URL と、ブラウザへ預ける往復状態を返す。

        ``silent`` なら IdP に画面を出させない（``prompt=none``。ADR-0077 §9）。
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
        """切れたログインを画面を出さずに続ける往復（見えない枠の中。ADR-0104）。

        常に ``prompt=none``。``continued`` は手元に残っていた期限切れのトークンから読んだもので、
        戻ってきた人が同じなら、ロール・サインインした時刻を引き継ぐ。読めなければ ``None``
        （そのときは新しいログインとして入る）。
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
    """往復状態から認可要求の URL を組む。

    ログインの往復と連携の往復（ADR-0077 §5）で**まったく同じ**なので 1 か所に置く。
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
            silent=transaction.silent,
        )
    )
    return SsoAuthorizationDto(authorization_url=authorization_url, transaction=transaction)


__all__ = ["StartSsoLogin", "authorization_for"]
