"""マスタデータの整合性（正本ファイル内のドリフト検出）。"""

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


def test_admin_role_has_all_permissions() -> None:
    assert set(master_data.ROLE_PERMISSIONS["admin"]) == set(master_data.PERMISSION_CODES)


def test_default_admin_role_exists() -> None:
    assert master_data.DEFAULT_ADMIN_ROLE in {name for _, name in master_data.ROLES}


def test_default_admin_password_hash_matches_documented_password() -> None:
    """事前計算ハッシュと平文の対応を固定する（Domain は werkzeug を import できない）。"""
    assert check_password_hash(master_data.DEFAULT_ADMIN_PASSWORD_HASH, master_data.DEFAULT_ADMIN_PASSWORD)


def test_only_admin_holds_the_whole_administration_core() -> None:
    """人とロールの両方を配れるのは admin だけ。ほかの雛形は系統をまたがない（ADR-0051）。"""
    from shared.domain.auth.authority import ADMINISTRATION_CORE

    holders = {role for role, codes in master_data.ROLE_PERMISSIONS.items() if set(ADMINISTRATION_CORE) <= set(codes)}
    assert holders == {"admin"}


def test_system_admin_touches_neither_people_nor_content() -> None:
    codes = set(master_data.ROLE_PERMISSIONS["system-admin"])
    assert not codes & {"user:manage", "role:manage", "permission:manage", "group:manage", "item:manage", "audit:view"}


def test_auditor_only_reads() -> None:
    assert all(code.endswith(":view") for code in master_data.ROLE_PERMISSIONS["auditor"])
