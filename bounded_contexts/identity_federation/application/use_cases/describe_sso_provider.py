"""Answer whether the login screen shows the "Sign in with SSO" button.

Called unauthenticated, so **no connection URL or client ID is returned**. Only
"is it usable" and "the name shown on the button".
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
    #: Whether sign-out is configured to go through to the IdP. **Meaningless if SSO is unusable**,
    #: so the setting isn't returned as is but folded together with ``enabled``.
    rp_logout_enabled: bool = False

    def execute(self) -> SsoProviderDto:
        usable = self.provider is not None and self.provider.is_usable
        return SsoProviderDto(
            enabled=usable,
            display_name=self.provider.display_name if usable and self.provider else "",
            rp_logout_enabled=usable and self.rp_logout_enabled,
        )


__all__ = ["DescribeSsoProvider"]
