"""IdP からの停止の通知を受け取る（OpenID Connect Back-Channel Logout 1.0。ADR-0036）。

この口が呼ばれるのは**利用者のブラウザからではない**。IdP のサーバーが直接叩く
サーバー間の経路で、届いた ``logout_token`` の署名だけが相手の証明になる。

やることは 1 つだけ ——「このセッションはもう使わせない」を記録する。
セッションの実体はサーバーに控えの無い JWT なので、ここで落とせるものが無い
（無効かどうかは、次にトークンが提示された時点で照合する）。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    LogoutTokenVerification,
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
    require_usable,
)
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import (
    LogoutNotice,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class ReceiveBackchannelLogout:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    revocations: SessionRevocationRepository
    #: 記録を残しておく秒数。**リフレッシュトークンの寿命**を渡す ——それを過ぎれば
    #: 記録より前に発行されたトークンは自力で期限切れになり、行を持つ意味が無くなる。
    keep_for_seconds: int

    def execute(self, *, logout_token: str) -> LogoutNotice:
        provider = require_usable(self.provider)
        claims = self.gateway.verify_logout_token(LogoutTokenVerification(provider=provider, logout_token=logout_token))
        notice = LogoutNotice.from_claims(claims, issuer=provider.issuer)
        self.revocations.record(SessionRevocation.of(notice, now=utcnow(), keep_for_seconds=self.keep_for_seconds))
        return notice


__all__ = ["ReceiveBackchannelLogout"]
