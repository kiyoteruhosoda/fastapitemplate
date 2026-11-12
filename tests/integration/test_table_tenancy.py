"""Every table declares "whom it belongs to" (ADR-0079 §1 decision 6, ADR-0079 §2).

Forgetting to filter by tenant still works when left out, and is noticed only after a leak. Every
new table must declare one of "tenant table / per-user table / system table"; tables with no
declaration, or whose columns contradict the declaration, fail here.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from shared.infrastructure.models.tenancy import TENANCY_KEY, Tenancy
from shared.kernel.database.db import Base

# conftest registers every model (``_REGISTERED_MODELS``).
_TABLES = sorted(Base.metadata.tables.values(), key=lambda t: t.name)

#: Tenant tables whose ``tenant_id`` may be NULL, and why.
_NULLABLE_TENANT = {
    # Operations by the system administrator and failures with an unknown target belong to no tenant
    "audit_log",
}


def _kind(table: sa.Table) -> Tenancy | None:
    value = table.info.get(TENANCY_KEY)
    return Tenancy(value) if value is not None else None


def _points_at(column: sa.Column[object], target: str) -> bool:
    return any(fk.target_fullname == target for fk in column.foreign_keys)


@pytest.mark.parametrize("table", _TABLES, ids=lambda t: t.name)
def test_every_table_declares_whose_it_is(table: sa.Table) -> None:
    assert _kind(table) is not None, (
        f"{table.name} has no declaration. Add declared(Tenancy.TENANT) or similar to __table_args__"
        "（shared/infrastructure/models/tenancy.py）"
    )


@pytest.mark.parametrize("table", [t for t in _TABLES if _kind(t) is Tenancy.TENANT], ids=lambda t: t.name)
def test_a_tenant_table_has_the_tenant(table: sa.Table) -> None:
    column = table.columns.get("tenant_id")
    assert column is not None, f"{table.name} is a tenant table but has no tenant_id"
    if table.name in _NULLABLE_TENANT:
        return
    assert not column.nullable, f"{table.name}.tenant_id is nullable"
    assert _points_at(column, "tenants.id"), f"{table.name}.tenant_id does not reference tenants"


@pytest.mark.parametrize("table", [t for t in _TABLES if _kind(t) is Tenancy.PERSONAL], ids=lambda t: t.name)
def test_a_personal_table_follows_its_user(table: sa.Table) -> None:
    if table.name == "users":
        return
    column = table.columns.get("user_id")
    assert column is not None, f"{table.name} is a per-user table but has no user_id"
    assert _points_at(column, "users.id"), f"{table.name}.user_id does not reference users"


@pytest.mark.parametrize("table", [t for t in _TABLES if _kind(t) is not Tenancy.TENANT], ids=lambda t: t.name)
def test_only_tenant_tables_carry_a_tenant(table: sa.Table) -> None:
    """Having ``tenant_id`` without being declared a tenant table is a declaration error.

    (Only the membership table ``user_tenants`` has ``tenant_id`` as a per-user table.)
    """
    if table.name == "user_tenants":
        return
    assert "tenant_id" not in table.columns, f"{table.name} has tenant_id but is not a tenant table"
