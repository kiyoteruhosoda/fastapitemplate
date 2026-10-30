"""IdP が名乗った利用者を、このアプリの利用者へ結び付けてよいか（ADR-0077 §1 / ADR-0077 §4）。

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
    #: ⚠ **既定は寄せない**（ADR-0077 §4）。条件の ``email_verified`` は、assay では
    #: 「テナント管理者がそう主張している」であって本人の証明ではない。
    link_by_email: bool = False
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
        """既存の利用者へ寄せてよいか。**既定は寄せない**（ADR-0077 §4）。

        開けたときも**検証済みのメールアドレスに限る**。IdP が検証していない
        アドレスで寄せると、相手のアドレスを名乗るだけで他人のアカウントへ入れる。

        ⚠ **``email_verified`` の意味は IdP ごとに違う。** 自前 idp (assay) では
        この値が真になる経路は自己登録の確認メールだけで、**管理者によるメール変更は
        この値を維持する**。つまり「本人が所有を証明した」ではなく
        **「テナント管理者がそう主張している」**である。開けるなら、つないだ IdP で
        この値がどう立つのかまで確かめること。
        """
        return self.link_by_email and user.email_verified

    def may_claim_seat(self, user: FederatedUser) -> bool:
        """指名された席（入り口をまだ 1 つも持たない利用者）を、受け取ってよいか（ADR-0079 §5）。

        システム管理者が最初のテナント管理者をメールアドレスで指名すると、入り口の無い
        利用者が先にできる。**寄せる設定（``link_by_email``）とは別に**、検証済みのメール
        アドレスなら受け取らせる ——席には誰の入り口も無いので、寄せても誰かの口座を
        奪うことにはならない。
        """
        return user.email_verified


__all__ = ["AccountLinkingPolicy"]
