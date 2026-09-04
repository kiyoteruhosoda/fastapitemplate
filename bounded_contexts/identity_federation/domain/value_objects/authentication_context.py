"""要求した認証の強度（``acr_values``）と、返ってきた ``acr`` の突き合わせ。

**要求したら確かめる。さもなければ要求しない**（ADR-0026 決定 1）。``acr_values``
は送っただけでは何の保証にもならない —— IdP 側のポリシーの綴り違い 1 つで条件が
外れ、単要素のログインが黙って通る。RP がそれに気付ける唯一の手段が、返ってきた
``acr`` を要求と突き合わせることである。

⚠ **``amr`` は使わない。** RFC 8176 の ``amr`` は使われた方式の一覧であって強度では
ない。外部 IdP 経由（``fed``）はその先で何が使われたかを IdP 自身も知らないため、
値の並びから多要素かどうかは読み取れない。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAcrNotSatisfiedError,
)


@dataclass(frozen=True)
class RequestedAuthenticationContext:
    #: 要求する ``acr`` の候補。**空 = 要求しない**（既定）。
    values: tuple[str, ...] = ()

    @property
    def is_requested(self) -> bool:
        return bool(self.values)

    def ensure_satisfied(self, acr: object) -> None:
        """返ってきた ``acr`` が要求のいずれかと一致することを確かめる。

        ⚠ **``acr`` が返ってこない場合も断る。** 要求したのに保証が得られていない
        以上、通してはいけない。予約語を持たない IdP へつなぐ派生は、要求そのものを
        しない（``values`` を空にする）ことで従来どおり動く。
        """
        if not self.is_requested:
            return
        if not isinstance(acr, str) or acr not in self.values:
            raise SsoAcrNotSatisfiedError


__all__ = ["RequestedAuthenticationContext"]
