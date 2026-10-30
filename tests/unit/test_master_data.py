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
    """owner はテナント管理者。内側の全権限を持ち、全体の権限は持たない（ADR-0079 §1）。"""
    inside = set(master_data.PERMISSION_CODES) - set(master_data.SYSTEM_PERMISSIONS)
    assert set(master_data.ROLE_PERMISSIONS["owner"]) == inside


def test_only_system_roles_hold_system_permissions() -> None:
    """全体の権限をテナントの中のロールに持たせると、ほかのテナントまで動かせる。"""
    for role, codes in master_data.ROLE_PERMISSIONS.items():
        if role not in master_data.SYSTEM_ROLES:
            assert not set(codes) & set(master_data.SYSTEM_PERMISSIONS), role


def test_the_operator_holds_every_system_permission() -> None:
    codes = set(master_data.ROLE_PERMISSIONS[master_data.SYSTEM_ADMIN_ROLE])
    assert set(master_data.SYSTEM_PERMISSIONS) <= codes


def test_support_only_looks_at_the_state() -> None:
    """サポート担当は状態を見るだけ。設定・アプリログ・監査ログ・変える権限は持たない（ADR-0084 §2）。"""
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
    """変えられるなら見られる（見るだけの人を作れるよう、読むと変えるを分けてある。ADR-0084 §3）。"""
    for role, codes in master_data.ROLE_PERMISSIONS.items():
        for code in codes:
            if code.endswith(":write"):
                assert code.replace(":write", ":view") in codes, (role, code)


def test_default_admin_role_exists() -> None:
    assert master_data.DEFAULT_ADMIN_ROLE in {name for _, name in master_data.ROLES}


def test_default_admin_password_hash_matches_documented_password() -> None:
    """事前計算ハッシュと平文の対応を固定する（Domain は werkzeug を import できない）。"""
    assert check_password_hash(master_data.DEFAULT_ADMIN_PASSWORD_HASH, master_data.DEFAULT_ADMIN_PASSWORD)


def test_only_owner_holds_the_whole_administration_core() -> None:
    """人とロールの両方を配れるのは owner だけ。ほかの雛形は系統をまたがない（ADR-0078 §4）。"""
    from shared.domain.auth.authority import ADMINISTRATION_CORE

    holders = {role for role, codes in master_data.ROLE_PERMISSIONS.items() if set(ADMINISTRATION_CORE) <= set(codes)}
    assert holders == {"owner"}


def test_system_admin_touches_neither_people_nor_content() -> None:
    """システム管理者は中身を見られない（ADR-0079 §1）。監査ログは全体の記録だけが見える。"""
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
