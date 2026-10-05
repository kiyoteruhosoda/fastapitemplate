"""管理 API の「権限を動かす操作」に掛ける関門（ADR-0051）。

scope の検査（``require_permission``）が答えるのは「この画面を使えるか」まで。
ここで答えるのは、その画面で**この相手に・この権限を**動かしてよいか。

- 自分が持っていない権限は、配ることも取り上げることもできない
- 自分より多くの権限を持つ利用者には触れない
- 自分のロールを変える・自分を止める・自分を消すことはできない
- 「管理の要」を持つ有効な利用者を 0 人にする変更は通さない

操作する人とリクエストの DB セッションを 1 つにまとめた :class:`Administration`
として受け取る（関門はどれも、この 2 つを材料にする）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from presentation.fastapi.dependencies.auth import get_current_principal
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.domain.auth.authority import beyond
from shared.infrastructure.administrator_census import count_active_administrators
from shared.infrastructure.models import Role, User
from shared.kernel.database.session import get_db


def permissions_of(roles: Iterable[Role]) -> frozenset[str]:
    """ロールの束が持つ権限の和集合。"""
    return frozenset(p.code for role in roles for p in role.permissions)


@dataclass(frozen=True)
class Administration:
    """誰が（``actor``）、どのセッションで（``db``）管理の操作をしているか。"""

    actor: AuthenticatedPrincipal
    db: Session

    def ensure_within_authority(self, required: Iterable[str]) -> None:
        """``required`` をすべて操作する人が持っていなければ 403。

        比べるのは**いま有効な権限**（アクティブロールで絞った後。ADR-0017）である。
        弱いロールで操作している間は、強い権限は配れない。
        """
        missing = beyond(self.actor.permissions, required)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "beyond_your_permissions", "permissions": sorted(missing)},
            )

    def ensure_not_yourself(self, user: User) -> None:
        """自分のロール・有効状態・存在は、管理画面から変えさせない。

        自分を締め出す事故を防ぐのと、権限の変更には必ず別の人の手を通すため。
        """
        if user.id == self.actor.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "cannot_change_yourself"},
            )

    def ensure_an_administrator_remains(self) -> None:
        """変更を ``flush`` して数え直す。「管理の要」を持つ有効な利用者が 0 人なら 409。

        アクセストークンは寿命まで通るので（ADR-0041）、ロールを外された人の古い
        1 枚でも、ここまでの関門は通り抜けうる。最後はいまの DB の状態で確かめる。
        例外はリクエストのセッションを rollback させるので、変更は残らない。
        """
        self.db.flush()
        if count_active_administrators(self.db) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "last_administrator"},
            )


def get_administration(
    actor: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Administration:
    return Administration(actor=actor, db=db)


AdministrationDep = Annotated[Administration, Depends(get_administration)]

__all__ = ["Administration", "AdministrationDep", "get_administration", "permissions_of"]
