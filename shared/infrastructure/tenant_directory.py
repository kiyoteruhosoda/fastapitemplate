"""Look up and set up the tenant registry (``tenants``) (ADR-0079 §1)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import Tenant, User

#: Short name of the "default tenant" created when migrating an existing environment (ADR-0079 §1 decision 9).
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default"


def tenant_of_issuer(session: Session, issuer: str) -> int | None:
    """Tenant for the issuer. ``None`` if not registered (such tokens are not accepted)."""
    if not issuer:
        return None
    return session.scalar(sa.select(Tenant.id).where(Tenant.issuer == issuer))


def tenant_of_slug(session: Session, slug: str) -> int | None:
    """Tenant for the short name. ``None`` if there is none."""
    return session.scalar(sa.select(Tenant.id).where(Tenant.slug == slug))


def tenant_named(session: Session, slug: str) -> Tenant | None:
    return session.scalar(sa.select(Tenant).where(Tenant.slug == slug))


def tenant_issuing(session: Session, issuer: str) -> Tenant | None:
    """Tenant for the issuer (the whole row)."""
    if not issuer:
        return None
    return session.scalar(sa.select(Tenant).where(Tenant.issuer == issuer))


def sole_tenant(session: Session) -> Tenant | None:
    """The tenant if there is exactly one. ``None`` if there are two or more (or zero).

    In an environment with a single tenant, entry URLs need not name the tenant (ADR-0079 §1
    decision 8).
    """
    tenants = session.scalars(sa.select(Tenant).limit(2)).all()
    return tenants[0] if len(tenants) == 1 else None


def entrance_tenant(session: Session, slug: str | None) -> Tenant | None:
    """Tenant chosen at the entry. Without a name, the only tenant when there is exactly one."""
    return tenant_named(session, slug) if slug else sole_tenant(session)


def ensure_default_tenant(session: Session, *, issuer: str, client_id: str) -> Tenant:
    """Create the default tenant if it does not exist.

    For setup (the seed script) and tests. In running environments the migration
    (``0015_tenants``) does the same.
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
    """Put the initial administrator (``owner``) into the default tenant. Leave them alone if they
    already belong somewhere.

    Call after ``ensure_default_admin`` (setup and recovery). The initial administrator is a tenant
    admin and cannot manage anything while outside the tenants (ADR-0079 §1).
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
    "entrance_tenant",
    "seat_default_admin",
    "sole_tenant",
    "tenant_issuing",
    "tenant_named",
    "tenant_of_issuer",
    "tenant_of_slug",
]
