"""連携先の外部 IdP（OpenID Provider）1 つ分の設定。

このアプリが持つ IdP は 1 つだけで、値は設定（``settings`` の ``OIDC_*``）から
組み立てる（ADR-0025）。ここは組み立て済みの値を受け取り、「使える設定か」と
「認可要求に載せる scope」だけを判断する。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.value_objects.client_credential import (
    ClientCredential,
)

# OpenID Connect は ``openid`` scope が無いと ID トークンを返さない。設定から
# 抜け落ちていても必ず要求する。
REQUIRED_SCOPE = "openid"


@dataclass(frozen=True)
class IdentityProvider:
    display_name: str
    issuer: str
    client_id: str
    credential: ClientCredential
    redirect_uri: str
    scopes: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """認可要求を始められるか（接続先と資格情報が揃っているか）。

        資格情報が揃っているかの判断は方式ごとに違うので
        :class:`ClientCredential` に任せる（ADR-0025）。
        """
        return bool(self.issuer and self.client_id and self.redirect_uri and self.credential.is_complete)

    @property
    def scope_parameter(self) -> str:
        """``scope`` パラメータの値。``openid`` を必ず先頭に置き、重複は畳む。"""
        requested = (REQUIRED_SCOPE, *(scope for scope in self.scopes if scope))
        return " ".join(dict.fromkeys(requested))


def require_usable(provider: IdentityProvider | None) -> IdentityProvider:
    """使える設定であることを確かめて返す。駄目なら :class:`SsoNotConfiguredError`。

    「無効」と「設定が埋まっていない」を呼び出し側から区別する必要はない
    （どちらも SSO を始められない、という 1 つの結果になる）。
    """
    if provider is None or not provider.is_usable:
        raise SsoNotConfiguredError
    return provider


__all__ = ["REQUIRED_SCOPE", "IdentityProvider", "require_usable"]
