"""テナントの台帳（``tenants``）を引く・据える（ADR-0061）。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import Tenant, User

#: 既存の環境を移すときに作る「既定のテナント」の短い名前（ADR-0061 決定 9）。
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default"


def tenant_of_issuer(session: Session, issuer: str) -> int | None:
    """発行者に当たるテナント。登録が無ければ ``None``（そのトークンは受け付けない）。"""
    if not issuer:
        return None
    return session.scalar(sa.select(Tenant.id).where(Tenant.issuer == issuer))


def tenant_of_slug(session: Session, slug: str) -> int | None:
    """短い名前に当たるテナント。無ければ ``None``。"""
    return session.scalar(sa.select(Tenant.id).where(Tenant.slug == slug))


def ensure_default_tenant(session: Session, *, issuer: str, client_id: str) -> Tenant:
    """既定のテナントが無ければ作る。

    据え付け（投入スクリプト）と試験のためのもの。動いている環境の移行は
    マイグレーション（``0015_tenants``）が同じことをする。
    """
    tenant = session.scalar(sa.select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
    if tenant is None:
        tenant = Tenant(
            slug=DEFAULT_TENANT_SLUG,
            display_name=DEFAULT_TENANT_NAME,
            issuer=issuer or None,
            client_id=client_id or None,
        )
        session.add(tenant)
        session.flush()
    return tenant


def seat_default_admin(session: Session, *, issuer: str, client_id: str) -> None:
    """初期管理者（``owner``）を既定のテナントへ入れる。既にどこかに居れば触らない。

    ``ensure_default_admin`` の後に呼ぶ（据え付けと復旧）。初期管理者はテナント管理者で、
    テナントに属さないままでは何も管理できない（ADR-0061）。
    """
    admin = session.scalar(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    if admin is None or admin.tenant_id is not None:
        return
    admin.join(ensure_default_tenant(session, issuer=issuer, client_id=client_id).id)
    session.flush()


__all__ = [
    "DEFAULT_TENANT_NAME",
    "DEFAULT_TENANT_SLUG",
    "ensure_default_tenant",
    "seat_default_admin",
    "tenant_of_issuer",
    "tenant_of_slug",
]
