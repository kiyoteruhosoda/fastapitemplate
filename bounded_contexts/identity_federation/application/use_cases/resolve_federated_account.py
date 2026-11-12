"""Resolve the IdP's identity to a user of this app.

In order, try

1. the user of the ``(issuer, subject)`` binding, if any
2. otherwise, merge into an existing local account by **verified** email
   (refuse if a user with the same address exists but merging isn't allowed; recreating would
   hit the email uniqueness constraint)
3. otherwise, create a new one (if allowed)

and if none applies, refuse the login. A record is kept in ``federated_identities`` once
bound or created, so from the second time on it is resolved by 1.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import (
    ResolvedAccountDto,
)
from bounded_contexts.identity_federation.domain.entities.federated_account import (
    FederatedAccount,
    NewFederatedAccount,
)
from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAccountInactiveError,
    SsoAccountNotLinkedError,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.repositories.federated_user_directory import (
    FederatedUserDirectory,
)
from bounded_contexts.identity_federation.domain.value_objects.account_linking_policy import (
    AccountLinkingPolicy,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_user import (
    FederatedUser,
)
from bounded_contexts.identity_federation.domain.value_objects.provisioning_policy import (
    ProvisioningPolicy,
)
from bounded_contexts.identity_federation.domain.value_objects.role_assignment import (
    RoleAssignment,
)


@dataclass(frozen=True)
class ResolveFederatedAccount:
    identities: FederatedIdentityRepository
    directory: FederatedUserDirectory
    linking: AccountLinkingPolicy
    policy: ProvisioningPolicy
    roles: RoleAssignment

    def execute(self, *, issuer: str, user: FederatedUser) -> ResolvedAccountDto:
        self.linking.ensure_accepted(user)
        known = self._known_account(issuer, user.subject)
        if known is not None:
            self._ensure_active(known)
            # ⚠ **The copy treats the IdP as the source of truth** (ADR-0077 §6). Without overwriting
            #   here, renames and email changes over there would leave the display stale forever.
            self.directory.refresh_profile(known.user_id, email=user.email, username=user.username)
            self._synchronize_roles(known)
            return ResolvedAccountDto(user_id=known.user_id)
        return self._attach(issuer, user)

    # ------------------------------------------------------------------
    # User already bound
    # ------------------------------------------------------------------

    def _known_account(self, issuer: str, subject: str) -> FederatedAccount | None:
        identity = self.identities.find(issuer, subject)
        if identity is None:
            return None
        account = self.directory.find_by_id(identity.user_id)
        if account is None:
            # The user was deleted but the binding remains. Recreate on the next login.
            return None
        self.identities.touch(identity)
        return account

    def _synchronize_roles(self, account: FederatedAccount) -> None:
        """Re-fetch roles every time, only when operating with the IdP as source of truth.

        By default (``sync_on_login`` false) roles are left alone, so roles added on the admin
        screen aren't stripped on every login.
        """
        if not self.roles.sync_on_login:
            return
        self.directory.apply_roles(account.user_id, self.roles.roles())

    # ------------------------------------------------------------------
    # Party not yet bound
    # ------------------------------------------------------------------

    def _attach(self, issuer: str, user: FederatedUser) -> ResolvedAccountDto:
        # ⚠ **This is the only place an email is required** (ADR-0077 §6). Already bound parties
        #   are looked up by ``sub``, so they can sign in without one.
        if user.email is None:
            # Can't find a user to merge into, and can't create one either (``users.email`` is required).
            # ⚠ **Don't distinguish the reasons** — what the person can do is the same: "ask an admin".
            raise SsoAccountNotLinkedError
        existing = self.directory.find_by_email(user.email)
        if existing is not None:
            return self._link_existing(issuer, user, existing)

        if not self.policy.auto_provision:
            raise SsoAccountNotLinkedError
        created = self.directory.provision(
            NewFederatedAccount(
                email=user.email,
                username=user.username,
                roles=self.roles.roles(),
            )
        )
        self._link(issuer, user, created.user_id)
        return ResolvedAccountDto(user_id=created.user_id, provisioned=True)

    def _link_existing(self, issuer: str, user: FederatedUser, existing: FederatedAccount) -> ResolvedAccountDto:
        """When a user with the same email already exists.

        If merging isn't allowed, **refuse without recreating**. Emails are unique, so trying to
        create a new one here would hit the uniqueness constraint and become a 500.
        """
        claims_seat = existing.awaiting_owner and self.linking.may_claim_seat(user)
        if not (self.linking.may_link(user) or claims_seat):
            raise SsoAccountNotLinkedError
        self._ensure_active(existing)
        self._link(issuer, user, existing.user_id)
        return ResolvedAccountDto(user_id=existing.user_id, linked=True)

    def _link(self, issuer: str, user: FederatedUser, user_id: int) -> None:
        self.identities.link(FederatedIdentity(issuer=issuer, subject=user.subject, user_id=user_id))

    @staticmethod
    def _ensure_active(account: FederatedAccount) -> None:
        if not account.is_active:
            raise SsoAccountInactiveError


__all__ = ["ResolveFederatedAccount"]
