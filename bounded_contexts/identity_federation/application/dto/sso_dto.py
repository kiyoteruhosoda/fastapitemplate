"""ID 連携ユースケースの入出力（Presentation 層はこれを Pydantic へ写す）。"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)


@dataclass(frozen=True)
class SsoProviderDto:
    """ログイン画面に「SSO で入る」ボタンを出すかどうかの判断材料。"""

    enabled: bool
    display_name: str


@dataclass(frozen=True)
class SsoAuthorizationDto:
    """IdP へ送り出すための材料。

    ``transaction`` は送り出したブラウザの Cookie へ署名して預ける往復状態で、
    戻ってきたときに「同じブラウザか」を確かめるために使う（ログイン CSRF を
    止める）。サーバー側に控えは残らない（ADR-0025）。
    """

    authorization_url: str
    transaction: LoginTransaction


@dataclass(frozen=True)
class ResolvedAccountDto:
    """IdP の名乗りを、このアプリの利用者へ落とした結果。

    ``provisioned`` / ``linked`` は監査ログのための区別（初めて作ったのか、
    既にあるアカウントへ結び付けたのか）。
    """

    user_id: int
    provisioned: bool = False
    linked: bool = False


@dataclass(frozen=True)
class SsoHandoffDto:
    """コールバックが SPA へ渡すもの（引き換え券と戻り先）。"""

    ticket: str
    redirect_to: str
    account: ResolvedAccountDto


@dataclass(frozen=True)
class SsoSessionDto:
    """引き換え券から取り出したログイン結果。"""

    user_id: int
    redirect_to: str


__all__ = [
    "ResolvedAccountDto",
    "SsoAuthorizationDto",
    "SsoHandoffDto",
    "SsoProviderDto",
    "SsoSessionDto",
]
