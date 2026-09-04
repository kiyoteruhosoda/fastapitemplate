"""ログイン画面へ「SSO で入る」ボタンを出すかどうかを答える。

未認証で呼ばれるため、**接続先の URL やクライアント ID は返さない**。返すのは
「使えるか」と「ボタンに出す名前」だけ。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import SsoProviderDto
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)


@dataclass(frozen=True)
class DescribeSsoProvider:
    provider: IdentityProvider | None

    def execute(self) -> SsoProviderDto:
        usable = self.provider is not None and self.provider.is_usable
        return SsoProviderDto(
            enabled=usable,
            display_name=self.provider.display_name if usable and self.provider else "",
        )


__all__ = ["DescribeSsoProvider"]
