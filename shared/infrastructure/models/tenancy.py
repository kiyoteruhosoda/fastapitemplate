"""Per-table declaration of "whose it is" (ADR-0079 §1 decision 6, ADR-0079 §2).

Every table declares one of the following three in ``info``. Tables without a declaration, or
whose columns contradict it, fail ``tests/integration/test_table_tenancy.py``.

- :attr:`Tenancy.TENANT` -- tenant content. Has ``tenant_id``; reads and writes are always
  filtered by the principal's tenant (the filtering is done at the repository entry)
- :attr:`Tenancy.PERSONAL` -- belongs to one user. Follows the user via ``user_id``, and the
  tenant is determined through the user (the users table ``users`` itself is here too)
- :attr:`Tenancy.GLOBAL` -- app-wide (tenants, role templates, settings, application logs)

Derived apps adding tables declare one of these too. When in doubt, ``TENANT``.
"""

from __future__ import annotations

from enum import StrEnum

TENANCY_KEY = "tenancy"


class Tenancy(StrEnum):
    TENANT = "tenant"
    PERSONAL = "personal"
    GLOBAL = "global"


def tenancy_info(kind: Tenancy) -> dict[str, Tenancy]:
    """Declaration to pass to ``sa.Table(..., info=...)``."""
    return {TENANCY_KEY: kind}


def declared(kind: Tenancy) -> dict[str, dict[str, Tenancy]]:
    """Declaration to pass to ``__table_args__``."""
    return {"info": tenancy_info(kind)}


__all__ = ["TENANCY_KEY", "Tenancy", "declared", "tenancy_info"]
