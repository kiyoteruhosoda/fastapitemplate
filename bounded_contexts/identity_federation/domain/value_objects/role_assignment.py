"""IdP のグループ -> このアプリのロールの割り当て。

認可そのものは scope（権限コード）で行う（CLAUDE.md「権限管理」）。IdP から
受け取るのはグループ名までで、それを**ロール**へ写すところまでがこの値オブジェクト
の責務。scope はロールが持つ権限としてすでに決まっている。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# 設定（``OIDC_ROLE_MAPPING``）の 1 行の区切り。"<グループ>=<ロール>"
_RULE_SEPARATOR = "="


@dataclass(frozen=True)
class RoleAssignment:
    """``group_to_roles`` に当たったロールと ``default_roles`` の和を与える。

    ``sync_on_login`` が真なら毎回のログインで引き直す（IdP を正とする）。偽なら
    アカウントを作るときにだけ与え、以後は管理画面での付与を残す。
    """

    default_roles: tuple[str, ...] = ()
    group_to_roles: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    sync_on_login: bool = False

    @classmethod
    def from_rules(cls, rules: Sequence[str], defaults: Sequence[str], *, sync_on_login: bool) -> RoleAssignment:
        """``["wiki-admins=admin", "staff=member"]`` の形の設定から組み立てる。

        区切りの無い行・空の行は黙って捨てる（設定の書き損じでログインが
        止まらないようにする）。
        """
        mapping: dict[str, tuple[str, ...]] = {}
        for rule in rules:
            group, separator, role = rule.partition(_RULE_SEPARATOR)
            if not separator or not group.strip() or not role.strip():
                continue
            mapping[group.strip()] = (*mapping.get(group.strip(), ()), role.strip())
        return cls(
            default_roles=tuple(dict.fromkeys(role for role in defaults if role)),
            group_to_roles=mapping,
            sync_on_login=sync_on_login,
        )

    def roles_for(self, groups: Sequence[str]) -> tuple[str, ...]:
        """与えるロール。既定のロールと、グループから引いたロールの和集合。"""
        matched = (role for group in groups for role in self.group_to_roles.get(group, ()))
        return tuple(dict.fromkeys((*self.default_roles, *matched)))

    @property
    def maps_groups(self) -> bool:
        return bool(self.group_to_roles)


__all__ = ["RoleAssignment"]
