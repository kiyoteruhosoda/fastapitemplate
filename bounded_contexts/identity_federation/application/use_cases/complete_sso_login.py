"""SSO ログインの完了（IdP からの戻りを受け取り、引き換え券を発行する）。

ブラウザから復元した往復状態と ``state`` を突き合わせ、認可コードを検証済みの
クレームへ換え、利用者を決めてから短命の引き換え券を返す。トークンそのものは
ここでは発行しない（発行は Presentation 層の :class:`TokenService`。券をトークンへ
換えるのは
:class:`~bounded_contexts.identity_federation.application.use_cases.exchange_sso_ticket.ExchangeSsoTicket`）。

**要求した認証の強度は、ここで確かめる。** ``acr_values`` を送ったのに満たされて
いない ID トークンを受け入れると、要求は「送っただけ」になり、IdP 側のポリシーの
綴り違い 1 つで単要素のログインが黙って通る（ADR-0026 決定 1）。
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
    #: 要求した ``acr_values`` と、返ってきた ``acr`` の突き合わせ（ADR-0026 決定 1）。
    #: 既定（何も要求しない）は :meth:`dataclasses.field` の ``default_factory`` で作る
    #: ——値オブジェクトを既定値としてクラス本体に置くと評価が 1 回きりになる。
    requested_context: RequestedAuthenticationContext = field(default_factory=RequestedAuthenticationContext)

    def execute(
        self,
        *,
        code: str,
        state: str,
        transaction: LoginTransaction | None,
    ) -> SsoHandoffDto:
        provider = require_usable(self.provider)
        if transaction is None or not transaction.matches(state):
            # 往復状態を復元できない = 送り出したブラウザからの戻りではない
            # （あるいは Cookie が落ちた・期限が切れた）。
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
        account = self.accounts.execute(issuer=provider.issuer, user=self.claims.apply(claims))
        ticket = new_secret()
        self.tickets.issue(
            SsoLoginTicket(
                ticket_hash=hash_secret(ticket),
                user_id=account.user_id,
                redirect_to=transaction.redirect_to,
                expires_at=utcnow() + timedelta(seconds=self.ticket_ttl_seconds),
            )
        )
        return SsoHandoffDto(ticket=ticket, redirect_to=transaction.redirect_to, account=account)


__all__ = ["CompleteSsoLogin"]
