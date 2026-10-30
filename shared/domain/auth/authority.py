"""権限を配る・取り上げるときの規則（ADR-0078 §4）。

ロールを付け外しする・ロールの中身を変える・利用者を止める操作は、それ自体が
「権限を動かす」操作である。ここには、その操作が**操作する人の権限の範囲に
収まっているか**を判定する純粋な規則だけを置く（DB・フレームワークに依存しない）。
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from shared.domain.auth.master_data import ROLE_PERMISSIONS, SYSTEM_PERMISSIONS, SYSTEM_ROLES

# 「管理の要」。この 2 つを両方持つ人が居れば、ほかの権限はすべて配り直せる。
# 有効な利用者のうち、これを持つ人が 0 人になる変更は通さない。
ADMINISTRATION_CORE: tuple[str, ...] = ("user:manage", "role:manage")


def beyond(actor: Collection[str], required: Iterable[str]) -> frozenset[str]:
    """``required`` のうち ``actor`` が持っていない権限。空なら範囲内。

    **自分が持っていない権限は、配ることも取り上げることもできない。**
    付けるときに見ないと昇格の経路になり（``user:manage`` だけの人が自分に
    ``owner`` を付ける）、外すときに見ないと格上の人を無力化できる。
    """
    return frozenset(code for code in required if code not in actor)


def changed(before: Iterable[str], after: Iterable[str]) -> frozenset[str]:
    """付けた・外したもの（対称差）。どちらの向きでも権限を動かしている。"""
    return frozenset(before) ^ frozenset(after)


_SYSTEM_SEAT_PERMISSIONS = frozenset(code for role in SYSTEM_ROLES for code in ROLE_PERMISSIONS[role])


def within_the_seat(in_tenant: bool, granted: Iterable[str]) -> frozenset[str]:
    """座る場所（テナントの中か外か）で効く権限だけに絞る（ADR-0079 §1）。

    **システム管理者とテナント管理者は兼ねない。** ロールの付け方を誤っても、
    テナントの利用者に全体の権限は効かず、テナントに属さない利用者に内側の権限は効かない。
    ロールの付け外しの関門（``TenantMembers.roles``）と二重にしてある。
    """
    codes = frozenset(granted)
    if in_tenant:
        return codes - frozenset(SYSTEM_PERMISSIONS)
    return codes & _SYSTEM_SEAT_PERMISSIONS


__all__ = ["ADMINISTRATION_CORE", "beyond", "changed", "within_the_seat"]
