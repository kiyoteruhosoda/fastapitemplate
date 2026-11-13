"""Entry point for looking up users by email (ADR-0079 §1 decision 8, ADR-0079 §4).

Email addresses are unique **only within the same seat**: inside the same tenant, or among people
outside the tenants (system administrators). Another tenant may have someone with the same address
(just as the same person may exist in different assay tenants). So an email alone does not
identify a person; always say which seat to search.

How the entry (``/login``) decides:

- With a tenant name (``/t/<slug>/login``), search inside that tenant
- Otherwise, first people outside the tenants. If none, in a single-tenant environment, that tenant
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
    """User whose email matches in that seat (a tenant, or ``None`` = outside the tenants)."""
    return session.scalar(_seat(tenant_id).where(User.email == email))


def email_taken(session: Session, email: str, tenant_id: int | None, *, except_user_id: int | None = None) -> bool:
    """Whether someone else in the same seat has this email."""
    query = _seat(tenant_id).where(User.email == email)
    if except_user_id is not None:
        query = query.where(User.id != except_user_id)
    return session.scalar(query) is not None


def account_signing_in(session: Session, email: str, tenant_slug: str | None) -> User | None:
    """User trying to sign in at the entry (decided as above). ``None`` if not found."""
    if tenant_slug:
        tenant = tenant_named(session, tenant_slug)
        return account_with_email(session, email, tenant.id) if tenant is not None else None
    outsider = account_with_email(session, email, None)
    if outsider is not None:
        return outsider
    tenant = sole_tenant(session)
    return account_with_email(session, email, tenant.id) if tenant is not None else None


__all__ = ["account_signing_in", "account_with_email", "email_taken"]
