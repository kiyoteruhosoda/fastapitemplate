"""サインアウトを IdP まで通すための送り出し先を組み立てる（RP-Initiated Logout 1.0）。

**アプリのセッションを終わらせるのは別の仕事**（``POST /api/auth/logout``）。ここが
決めるのは「そのあとブラウザをどこへ送るか」だけで、送らない判断もここでする。

``None`` を返すのは次の 3 つ。どれも失敗ではないので、呼ぶ側は素直にアプリ内の
行き先（ログイン画面）へ戻すこと。

1. 設定が無効（``OIDC_RP_LOGOUT_ENABLED`` の既定）
2. SSO 自体が使えない
3. IdP が ``end_session_endpoint`` を出していない
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    EndSessionRequest,
    OidcProviderGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildRpLogoutUrl:
    provider: IdentityProvider | None
    gateway: OidcProviderGateway
    enabled: bool = False
    #: サインアウト後に IdP から戻ってくる先。空なら付けない。
    post_logout_redirect_uri: str = ""

    def execute(self) -> str | None:
        if not self.enabled:
            return None
        provider = self.provider
        if provider is None or not provider.is_usable:
            return None
        try:
            return self.gateway.end_session_url(
                EndSessionRequest(
                    provider=provider,
                    post_logout_redirect_uri=self.post_logout_redirect_uri,
                )
            )
        except IdentityProviderUnavailableError:
            # discovery が引けないことを理由にサインアウトを断らない。アプリ側の
            # セッションは既に終わっているので、**戻り先が無いだけ**にする。
            logger.warning("sso_end_session_unavailable")
            return None


__all__ = ["BuildRpLogoutUrl"]
