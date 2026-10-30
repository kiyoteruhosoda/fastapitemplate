"""システム管理者とテナント管理者を兼ねさせない規則（ADR-0079 §1 決定 4）。"""

from __future__ import annotations

from shared.domain.auth import master_data
from shared.domain.auth.authority import roles_fit_the_seat, within_the_seat


def test_a_tenant_member_never_carries_system_permissions() -> None:
    granted = {"item:view", "system-settings:write", "tenant:manage", "log:view"}
    assert within_the_seat(True, granted) == {"item:view"}


def test_someone_outside_any_tenant_carries_only_system_permissions() -> None:
    granted = set(master_data.ROLE_PERMISSIONS["owner"]) | {"tenant:manage"}
    assert within_the_seat(False, granted) == {"tenant:manage", "audit:view", "dashboard:view", "gui:view"}


def test_roles_fit_the_seat() -> None:
    assert roles_fit_the_seat(True, ["owner", "member"])
    assert not roles_fit_the_seat(True, ["owner", "system-admin"])
    assert roles_fit_the_seat(False, ["system-admin"])
    assert not roles_fit_the_seat(False, ["system-admin", "owner"])
