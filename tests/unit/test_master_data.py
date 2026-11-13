"""Master data consistency (detecting drift within the source-of-truth file)."""

from werkzeug.security import check_password_hash

from shared.domain.auth import master_data


def test_role_permissions_reference_known_codes() -> None:
    known = set(master_data.PERMISSION_CODES)
    for role, codes in master_data.ROLE_PERMISSIONS.items():
        unknown = set(codes) - known
        assert not unknown, f"role {role} references unknown codes: {unknown}"


def test_every_role_has_permission_assignment() -> None:
    role_names = {name for _, name in master_data.ROLES}
    assert role_names == set(master_data.ROLE_PERMISSIONS)


def test_owner_holds_everything_inside_the_tenant() -> None:
    """owner is the tenant administrator: has every inner permission and no system-wide one (ADR-0079 §1)."""
    inside = set(master_data.PERMISSION_CODES) - set(master_data.SYSTEM_PERMISSIONS)
    assert set(master_data.ROLE_PERMISSIONS["owner"]) == inside


def test_only_system_roles_hold_system_permissions() -> None:
    """A system-wide permission on a role inside a tenant would let it affect other tenants."""
    for role, codes in master_data.ROLE_PERMISSIONS.items():
        if role not in master_data.SYSTEM_ROLES:
            assert not set(codes) & set(master_data.SYSTEM_PERMISSIONS), role


def test_the_operator_holds_every_system_permission() -> None:
    codes = set(master_data.ROLE_PERMISSIONS[master_data.SYSTEM_ADMIN_ROLE])
    assert set(master_data.SYSTEM_PERMISSIONS) <= codes


def test_support_only_looks_at_the_state() -> None:
    """Support only views status: no settings, app logs, audit logs or write permissions (ADR-0084 §2)."""
    assert set(master_data.ROLE_PERMISSIONS["system-support"]) == {
        "system:view",
        "tenant:view",
        "dashboard:view",
        "gui:view",
    }


def test_content_admin_sets_the_rules_but_does_not_edit_content() -> None:
    codes = set(master_data.ROLE_PERMISSIONS["content-admin"])
    assert {"content-settings:view", "content-settings:write"} <= codes
    assert not codes & {"item:write", "note:write", "notification:send", "user:manage", "role:manage"}


def test_every_write_has_a_view() -> None:
    """Can change implies can view (view and write are split so view-only people can exist; ADR-0084 §3)."""
    for role, codes in master_data.ROLE_PERMISSIONS.items():
        for code in codes:
            if code.endswith(":write"):
                assert code.replace(":write", ":view") in codes, (role, code)


def test_default_admin_role_exists() -> None:
    assert master_data.DEFAULT_ADMIN_ROLE in {name for _, name in master_data.ROLES}


def test_default_admin_password_hash_matches_documented_password() -> None:
    """Pins the precomputed hash to its plaintext (Domain cannot import werkzeug)."""
    assert check_password_hash(master_data.DEFAULT_ADMIN_PASSWORD_HASH, master_data.DEFAULT_ADMIN_PASSWORD)


def test_only_owner_holds_the_whole_administration_core() -> None:
    """Only owner can grant both people and roles. Other templates do not cross lines (ADR-0078 §4)."""
    from shared.domain.auth.authority import ADMINISTRATION_CORE

    holders = {role for role, codes in master_data.ROLE_PERMISSIONS.items() if set(ADMINISTRATION_CORE) <= set(codes)}
    assert holders == {"owner"}


def test_system_admin_touches_neither_people_nor_content() -> None:
    """The system administrator cannot see contents (ADR-0079 §1); only system-wide audit records."""
    codes = set(master_data.ROLE_PERMISSIONS["system-admin"])
    assert not codes & {
        "user:manage",
        "role:manage",
        "group:manage",
        "item:view",
        "item:write",
        "note:view",
        "note:write",
        "notification:send",
        "content-settings:view",
        "content-settings:write",
    }


def test_auditor_only_reads() -> None:
    assert all(code.endswith(":view") for code in master_data.ROLE_PERMISSIONS["auditor"])
