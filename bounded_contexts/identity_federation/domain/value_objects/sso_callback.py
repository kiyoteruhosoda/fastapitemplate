"""IdP からの戻り（``code`` / ``state`` と、ブラウザから復元した往復状態）。

ログインの完了と連携の完了（ADR-0040）で同じ 3 つを受け取るので、値としてまとめる。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)


@dataclass(frozen=True)
class SsoCallback:
    code: str
    state: str
    #: 復元できなかった場合は ``None``（受け取る側が断る）。
    transaction: LoginTransaction | None


__all__ = ["SsoCallback"]
