"""IdP で入った利用者へ与えるロール。

認可そのものは scope（権限コード）で行う（CLAUDE.md「権限管理」）。ここが決めるのは
**どのロールを与えるか**までで、scope はロールが持つ権限としてすでに決まっている。

⚠ **グループからは引かない**（ADR-0042 / idp の ADR-0049 G7）。自前 idp (assay) は
``groups`` クレームを発行しないので、**設定として存在するのに一度も効かない**状態に
なっていた。idp の ADR-0049 は I6 として「**権限は RP が持つ。IdP は配らない**」と
決めているので、引く側を消すのが筋である。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleAssignment:
    """IdP で入った利用者へ与える既定のロール。

    ``sync_on_login`` が真なら毎回のログインで引き直す。⚠ **引き直すのは既定の
    ロールだけなので、管理画面で足したロールは毎回のログインで消える。** 管理画面で
    運用するなら偽にすること（既定は偽）。
    """

    default_roles: tuple[str, ...] = ()
    sync_on_login: bool = False

    @classmethod
    def from_rules(cls, defaults: Sequence[str], *, sync_on_login: bool) -> RoleAssignment:
        return cls(
            default_roles=tuple(dict.fromkeys(role for role in defaults if role)),
            sync_on_login=sync_on_login,
        )

    def roles(self) -> tuple[str, ...]:
        """与えるロール。"""
        return self.default_roles


__all__ = ["RoleAssignment"]
