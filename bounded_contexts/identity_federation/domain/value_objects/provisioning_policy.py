"""知らない相手を、このアプリの利用者として**作ってよいか**（ADR-0025）。

「受け入れてよいか」「寄せてよいか」は
:class:`~bounded_contexts.identity_federation.domain.value_objects.account_linking_policy.AccountLinkingPolicy`
が持つ。ここは作成の可否だけを決める。

⚠ **既定は作らない。** IdP がテナント共用のとき、作る設定は「IdP に口座がある人は
全員このアプリに入れる」を意味する。テンプレートは安全側へ倒し、開けたい派生が
``OIDC_AUTO_PROVISION`` を開ける。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvisioningPolicy:
    auto_provision: bool = False


__all__ = ["ProvisioningPolicy"]
