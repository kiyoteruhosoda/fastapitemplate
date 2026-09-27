"""連携の開始 ——**既にログインしている利用者**の IdP 往復を始める（ADR-0040）。

ログインの往復との違いは往復状態だけで、IdP へ送る認可要求は同じものになる
（戻り先の URI も 1 つしか登録しない）。往復状態には

- ``purpose = LINK`` —— 戻ってきたときにどちらの後始末をするかの目印
- ``user_id`` —— **始めた本人**

を入れる。⚠ **``user_id`` を入れるのがこの往復の要である。** これが無いと、
往復の途中で入れ替わったブラウザが、戻ってきたときに**別人の口座へ**結び付ける。
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
    #: 認可要求に載せる ``acr_values``（空 = 要求しない）。ADR-0026 決定 1。
    acr_values: tuple[str, ...] = ()

    def execute(self, *, user_id: int) -> SsoAuthorizationDto:
        provider = require_usable(self.provider)
        transaction = LoginTransaction(
            state=new_secret(),
            nonce=new_secret(),
            code_verifier=new_code_verifier(),
            purpose=TransactionPurpose.LINK,
            user_id=user_id,
        )
        return authorization_for(provider, self.gateway, transaction, self.acr_values)


__all__ = ["StartSsoLink"]
