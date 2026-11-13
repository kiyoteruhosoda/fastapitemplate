"""Rule that a system administrator cannot also be a tenant administrator (ADR-0079 §1 decision 4)."""

from __future__ import annotations

from shared.domain.auth import master_data
from shared.domain.auth.authority import within_the_seat


def test_a_tenant_member_never_carries_system_permissions() -> None:
    granted = {"item:view", "system-settings:write", "tenant:manage", "log:view"}
    assert within_the_seat(True, granted) == {"item:view"}


def test_someone_outside_any_tenant_carries_only_system_permissions() -> None:
    granted = set(master_data.ROLE_PERMISSIONS["owner"]) | {"tenant:manage"}
    assert within_the_seat(False, granted) == {"tenant:manage", "audit:view", "dashboard:view", "gui:view"}
