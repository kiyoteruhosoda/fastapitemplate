"""Whether an unknown party **may be created** as a user of this app (ADR-0077 §1).

"May it be accepted" and "may it be merged" are held by
:class:`~bounded_contexts.identity_federation.domain.value_objects.account_linking_policy.AccountLinkingPolicy`
This only decides whether creation is allowed.

⚠ **Default is not to create.** When the IdP is shared across tenants, enabling creation means
"everyone with an account at the IdP can get into this app". The template leans safe; derived
apps that want it open enable ``OIDC_AUTO_PROVISION``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvisioningPolicy:
    auto_provision: bool = False


__all__ = ["ProvisioningPolicy"]
