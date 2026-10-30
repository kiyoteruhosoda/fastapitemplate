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


def test_owner_holds_everything_inside_the_tenant() -> None:
    """owner はテナント管理者。内側の全権限を持ち、全体の権限は持たない（ADR-0061）。"""
    inside = set(master_data.PERMISSION_CODES) - set(master_data.SYSTEM_PERMISSIONS)
    assert set(master_data.ROLE_PERMISSIONS["owner"]) == inside


def test_only_system_roles_hold_system_permissions() -> None:
    """全体の権限をテナントの中のロールに持たせると、ほかのテナントまで動かせる。"""
    for role, codes in master_data.ROLE_PERMISSIONS.items():
        if role in master_data.SYSTEM_ROLES:
            assert set(master_data.SYSTEM_PERMISSIONS) <= set(codes)
        else:
            assert not set(codes) & set(master_data.SYSTEM_PERMISSIONS), role


def test_default_admin_role_exists() -> None:
    assert master_data.DEFAULT_ADMIN_ROLE in {name for _, name in master_data.ROLES}


def test_default_admin_password_hash_matches_documented_password() -> None:
    """事前計算ハッシュと平文の対応を固定する（Domain は werkzeug を import できない）。"""
    assert check_password_hash(master_data.DEFAULT_ADMIN_PASSWORD_HASH, master_data.DEFAULT_ADMIN_PASSWORD)


def test_only_owner_holds_the_whole_administration_core() -> None:
    """人とロールの両方を配れるのは owner だけ。ほかの雛形は系統をまたがない（ADR-0051）。"""
    from shared.domain.auth.authority import ADMINISTRATION_CORE

    holders = {role for role, codes in master_data.ROLE_PERMISSIONS.items() if set(ADMINISTRATION_CORE) <= set(codes)}
    assert holders == {"owner"}


def test_system_admin_touches_neither_people_nor_content() -> None:
    """システム管理者は中身を見られない（ADR-0061）。監査ログは全体の記録だけが見える。"""
    codes = set(master_data.ROLE_PERMISSIONS["system-admin"])
    assert not codes & {
        "user:manage",
        "role:manage",
        "permission:manage",
        "group:manage",
        "item:view",
        "item:manage",
        "note:view",
        "note:write",
        "notification:send",
    }


def test_auditor_only_reads() -> None:
    assert all(code.endswith(":view") for code in master_data.ROLE_PERMISSIONS["auditor"])
