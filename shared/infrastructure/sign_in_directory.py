"""メールアドレスで利用者を引く入口（ADR-0061 決定 8・ADR-0064）。

メールアドレスの一意は**同じ席の中だけ**: 同じテナントの中、またはテナントに属さない人
（システム管理者）の中。別のテナントには同じメールアドレスの人が居てよい（assay の別の
テナントに同じ人が居るのと同じ）。だから、メールアドレスだけでは人は決まらない ——
どの席で探すかを必ず添える。

入口（``/login``）の決め方:

- テナントの名前（``/t/<slug>/login``）があれば、そのテナントの中で探す
- 無ければ、まずテナントに属さない人。居なければ、テナントが 1 つだけの環境ではそのテナント
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.infrastructure.models import User, UserTenant
from shared.infrastructure.tenant_directory import sole_tenant, tenant_named


def _seat(tenant_id: int | None) -> sa.Select[User]:
    query = sa.select(User).outerjoin(UserTenant, UserTenant.user_id == User.id)
    if tenant_id is None:
        return query.where(UserTenant.user_id.is_(None))
    return query.where(UserTenant.tenant_id == tenant_id)


def account_with_email(session: Session, email: str, tenant_id: int | None) -> User | None:
    """その席（テナント、または ``None`` ＝ テナントの外）でメールアドレスが一致する利用者。"""
    return session.scalar(_seat(tenant_id).where(User.email == email))


def email_taken(session: Session, email: str, tenant_id: int | None, *, except_user_id: int | None = None) -> bool:
    """同じ席に、ほかにこのメールアドレスの人が居るか。"""
    query = _seat(tenant_id).where(User.email == email)
    if except_user_id is not None:
        query = query.where(User.id != except_user_id)
    return session.scalar(query) is not None


def account_signing_in(session: Session, email: str, tenant_slug: str | None) -> User | None:
    """入口で入ろうとしている利用者（上の決め方）。見つからなければ ``None``。"""
    if tenant_slug:
        tenant = tenant_named(session, tenant_slug)
        return account_with_email(session, email, tenant.id) if tenant is not None else None
    outsider = account_with_email(session, email, None)
    if outsider is not None:
        return outsider
    tenant = sole_tenant(session)
    return account_with_email(session, email, tenant.id) if tenant is not None else None


__all__ = ["account_signing_in", "account_with_email", "email_taken"]
