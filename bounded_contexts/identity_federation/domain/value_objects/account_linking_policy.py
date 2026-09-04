"""IdP が名乗った利用者を、このアプリの利用者へ結び付けてよいか（ADR-0025）。

ここが決めるのは 2 つだけ ——「受け入れてよい相手か」と「既存のローカル
アカウントへ寄せてよいか」。**作ってよいか**は別の判断なので
:class:`~bounded_contexts.identity_federation.domain.value_objects.provisioning_policy.ProvisioningPolicy`
が持つ。2 つを 1 つの値オブジェクトに混ぜると、「受け入れる／寄せる／作る」の
どれを緩めたのかが設定からも読み取れなくなる。
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
    link_by_email: bool = True
    allowed_email_domains: tuple[str, ...] = ()

    def ensure_accepted(self, user: FederatedUser) -> None:
        """受け入れてよい相手かを確かめる。駄目なら :class:`SsoEmailNotAllowedError`。

        ドメインを絞っていない（空）なら誰でも受け入れる。IdP 側で対象を絞って
        いる構成が普通なので、既定はここで重ねて絞らない。
        """
        if not self.allowed_email_domains:
            return
        if user.email_domain not in {domain.lower().lstrip("@") for domain in self.allowed_email_domains}:
            raise SsoEmailNotAllowedError

    def may_link(self, user: FederatedUser) -> bool:
        """既存の利用者へ寄せてよいか。

        **検証済みのメールアドレスに限る。** IdP が検証していないアドレスで寄せると、
        相手のアドレスを名乗るだけで他人のアカウントへ入れてしまう。
        """
        return self.link_by_email and user.email_verified


__all__ = ["AccountLinkingPolicy"]
