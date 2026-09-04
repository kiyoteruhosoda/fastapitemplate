"""IdP の名乗りを、このアプリの利用者へ落とす。

順に、

1. ``(issuer, subject)`` の結び付きがあればその利用者
2. 無ければ**検証済みの**メールアドレスで既存のローカルアカウントへ寄せる
   （同じアドレスの利用者が居るのに寄せてよくない場合は断る。作り直すと
   メールアドレスの一意制約に当たるため）
3. それも無ければ（許可されていれば）新しく作る

を試し、いずれでもなければログインを断る。結び付けた・作った時点で
``federated_identities`` に控えを残すので、2 回目以降は 1 で決まる。
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
            self._synchronize_roles(known, user)
            return ResolvedAccountDto(user_id=known.user_id)
        return self._attach(issuer, user)

    # ------------------------------------------------------------------
    # 既に結び付いている利用者
    # ------------------------------------------------------------------

    def _known_account(self, issuer: str, subject: str) -> FederatedAccount | None:
        identity = self.identities.find(issuer, subject)
        if identity is None:
            return None
        account = self.directory.find_by_id(identity.user_id)
        if account is None:
            # 利用者が消されたのに結び付きだけ残っている。次のログインで作り直す。
            return None
        self.identities.touch(identity)
        return account

    def _synchronize_roles(self, account: FederatedAccount, user: FederatedUser) -> None:
        """IdP を正とする運用のときだけ、ロールを毎回引き直す。

        既定（``sync_on_login`` が偽）では触らない。管理画面で足したロールを
        ログインのたびに剥がしてしまわないようにするため。
        """
        if not self.roles.sync_on_login:
            return
        self.directory.apply_roles(account.user_id, self.roles.roles_for(user.groups))

    # ------------------------------------------------------------------
    # まだ結び付いていない相手
    # ------------------------------------------------------------------

    def _attach(self, issuer: str, user: FederatedUser) -> ResolvedAccountDto:
        existing = self.directory.find_by_email(user.email)
        if existing is not None:
            return self._link_existing(issuer, user, existing)

        if not self.policy.auto_provision:
            raise SsoAccountNotLinkedError
        created = self.directory.provision(
            NewFederatedAccount(
                email=user.email,
                username=user.username,
                roles=self.roles.roles_for(user.groups),
            )
        )
        self._link(issuer, user, created.user_id)
        return ResolvedAccountDto(user_id=created.user_id, provisioned=True)

    def _link_existing(self, issuer: str, user: FederatedUser, existing: FederatedAccount) -> ResolvedAccountDto:
        """同じメールアドレスの利用者が既に居るとき。

        寄せてよい相手でなければ**作り直さずに断る**。メールアドレスは一意なので、
        ここで新しく作ろうとすると一意制約に当たって 500 になる。
        """
        if not self.linking.may_link(user):
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
