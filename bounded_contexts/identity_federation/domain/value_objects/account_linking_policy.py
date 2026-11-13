"""Whether a user claimed by the IdP may be bound to a user of this app (ADR-0077 §1 / ADR-0077 §4).

This decides just two things — "may the party be accepted" and "may it be merged into an
existing local account". **Whether creation is allowed** is a separate judgement held by
:class:`~bounded_contexts.identity_federation.domain.value_objects.provisioning_policy.ProvisioningPolicy`
Mixing them into one value object would make it impossible to tell from the settings which of
"accept / merge / create" was loosened.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoEmailNotAllowedError,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_user import (
    FederatedUser,
)


@dataclass(frozen=True)
class AccountLinkingPolicy:
    #: ⚠ **The default is not to merge** (ADR-0077 §4). The condition ``email_verified`` in assay
    #: means "a tenant admin claims so", not proof by the person.
    link_by_email: bool = False
    allowed_email_domains: tuple[str, ...] = ()

    def ensure_accepted(self, user: FederatedUser) -> None:
        """Check whether the party may be accepted. Otherwise :class:`SsoEmailNotAllowedError`.

        If domains aren't restricted (empty), anyone is accepted. Restricting on the IdP side is
        the usual setup, so by default no extra restriction is applied here.
        """
        if not self.allowed_email_domains:
            return
        if user.email_domain not in {domain.lower().lstrip("@") for domain in self.allowed_email_domains}:
            raise SsoEmailNotAllowedError

    def may_link(self, user: FederatedUser) -> bool:
        """Whether merging into an existing user is allowed. **Default is not to merge** (ADR-0077 §4).

        Even when enabled, **only verified emails**. Merging by an address the IdP hasn't verified
        would let anyone into another person's account just by claiming their address.

        ⚠ **What ``email_verified`` means differs per IdP.** In our own idp (assay) the only path
        that sets it true is the self-registration confirmation email, and **an admin's email change
        keeps the value**. So it means **"a tenant admin claims so"**, not "the person proved
        ownership". If enabling this, also verify how the connected IdP sets
        this value.
        """
        return self.link_by_email and user.email_verified

    def may_claim_seat(self, user: FederatedUser) -> bool:
        """Whether a designated seat (a user with no way in yet) may be claimed (ADR-0079 §5).

        When a system admin designates the first tenant admin by email, a user with no way in is
        created first. **Separately from the merge setting (``link_by_email``)**, a verified email is
        allowed to claim it — the seat has nobody's way in, so merging can't take over anyone's
        account.
        """
        return user.email_verified


__all__ = ["AccountLinkingPolicy"]
