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
