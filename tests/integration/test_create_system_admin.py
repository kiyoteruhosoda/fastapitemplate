"""最初のシステム管理者を作るスクリプト（``scripts/create_system_admin.py``。ADR-0079 §1・§3）。

テナントを入れた後の本番では、ここで作る 1 人目が居ないとテナントの台帳に誰も入れない。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.models import User
from tests.conftest import sign_in

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_system_admin.py"
_EMAIL = "ops@example.com"
_PASSWORD = "first-system-admin-1"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("create_system_admin", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args: str) -> int:
    return int(_script().main(["create_system_admin.py", *args]))


def _find(engine: sa.Engine, email: str) -> User | None:
    with Session(engine) as session:
        user = session.scalar(sa.select(User).where(User.email == email))
        if user is not None:
            # 閉じた後も読めるように、関係を先に引いておく
            _ = (user.role_names, user.tenant_id)
        return user


def test_the_first_system_administrator_can_sign_in_and_manage_tenants(
    engine: sa.Engine, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", _PASSWORD)
    assert _run(_EMAIL, "ops") == 0

    created = _find(engine, _EMAIL)
    assert created is not None
    assert created.username == "ops"
    assert created.role_names == tuple(master_data.SYSTEM_ROLES)
    # ⚠ テナントに属さない（属すとテナントの中の人になり、台帳に入れない）
    assert created.tenant_id is None

    sign_in(client, _EMAIL, _PASSWORD)
    assert client.get("/api/system/tenants").status_code == 200


def test_the_display_name_defaults_to_the_local_part(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", _PASSWORD)
    assert _run(_EMAIL) == 0
    created = _find(engine, _EMAIL)
    assert created is not None
    assert created.username == "ops"


@pytest.mark.parametrize("password", ["", "short-pass1"])
def test_a_short_password_is_refused_and_nothing_is_created(
    engine: sa.Engine, monkeypatch: pytest.MonkeyPatch, password: str
) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", password)
    assert _run(_EMAIL) == 2
    assert _find(engine, _EMAIL) is None


def test_missing_arguments_print_the_usage(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", _PASSWORD)
    assert _run() == 2


def test_running_it_again_changes_nothing(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """2 回目は同じメールアドレスの人を見つけて何もしない（パスワードを上書きしない）。"""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", _PASSWORD)
    assert _run(_EMAIL) == 0
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "another-password-123")
    assert _run(_EMAIL, "renamed") == 0

    with Session(engine) as session:
        people = session.scalars(sa.select(User).where(User.email == _EMAIL)).all()
        assert len(people) == 1
        assert people[0].username == "ops"
        assert people[0].password_hash is not None
        assert check_password_hash(people[0].password_hash, _PASSWORD)
