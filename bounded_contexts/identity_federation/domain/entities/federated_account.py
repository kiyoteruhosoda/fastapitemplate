"""SSO から見たこのアプリの利用者。

``shared`` の ``User`` モデルそのものではなく、ID 連携が必要とする項目だけを
持つ。Domain 層が SQLAlchemy のモデルに触れないようにするための境界で、実体との
やり取りは ``domain/repositories/federated_user_directory.py`` の
:class:`FederatedUserDirectory` が行う。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedAccount:
    user_id: int
    email: str
    is_active: bool
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewFederatedAccount:
    """これから作る利用者（初回ログインの自動プロビジョニング）。"""

    email: str
    username: str
    roles: tuple[str, ...] = ()


__all__ = ["FederatedAccount", "NewFederatedAccount"]
