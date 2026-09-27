"""連携の完了 ——戻ってきた ``(issuer, subject)`` を**いま入っている利用者**へ結び付ける。

ログインの完了（:class:`CompleteSsoLogin`）との違いは、利用者を**探さない**ことに
ある。誰に結び付けるかは往復を始めた時点で決まっていて、ここで決め直す余地は無い
（ADR-0040）。

断る場合は 3 つ。

- 往復状態が復元できない・``state`` が合わない —— 送り出したブラウザからの戻りではない
- 往復を始めた利用者と、いまのセッションが違う —— どちらへ結び付けるか決められない
- その ``(issuer, subject)`` が**別の利用者**に結び付いている —— 横取りになる
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
    #: 要求した ``acr_values`` と、返ってきた ``acr`` の突き合わせ（ADR-0026 決定 1）。
    requested_context: RequestedAuthenticationContext = field(default_factory=RequestedAuthenticationContext)

    def execute(self, *, callback: SsoCallback, user_id: int) -> FederatedIdentity:
        provider = require_usable(self.provider)
        transaction = callback.transaction
        if transaction is None or not transaction.matches(callback.state):
            raise SsoLoginTransactionInvalidError
        if not transaction.belongs_to(user_id):
            # ⚠ 往復の途中でサインアウトした・別の利用者で入り直した。**いまの
            #   セッションへ結び付け直さない** ——始めた本人以外の口座に入り口が生える。
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
            # 差し替えは黙って通さない。前の結び付きで入っていた経路が消えるため。
            raise SsoAlreadyLinkedError


__all__ = ["CompleteSsoLink"]
