"""全部の表が「誰のものか」を宣言しているか（ADR-0079 §1 決定 6・ADR-0079 §2）。

テナントの絞り忘れは、書き忘れても動いてしまい、気付くのは漏れた後になる。
表を足すたびに「テナントの表 / 利用者に付く表 / 全体の表」のどれかを宣言させ、
宣言の無い表と、宣言と列が食い違う表をここで落とす。
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from shared.infrastructure.models.tenancy import TENANCY_KEY, Tenancy
from shared.kernel.database.db import Base

# conftest が全モデルを登録している（``_REGISTERED_MODELS``）。
_TABLES = sorted(Base.metadata.tables.values(), key=lambda t: t.name)

#: ``tenant_id`` が NULL を取れるテナントの表と、その理由。
_NULLABLE_TENANT = {
    # システム管理者の操作・宛先の分からない失敗は、どのテナントのものでもない
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
        f"{table.name} に宣言がありません。__table_args__ に declared(Tenancy.TENANT) などを足してください"
        "（shared/infrastructure/models/tenancy.py）"
    )


@pytest.mark.parametrize("table", [t for t in _TABLES if _kind(t) is Tenancy.TENANT], ids=lambda t: t.name)
def test_a_tenant_table_has_the_tenant(table: sa.Table) -> None:
    column = table.columns.get("tenant_id")
    assert column is not None, f"{table.name} はテナントの表なのに tenant_id がありません"
    if table.name in _NULLABLE_TENANT:
        return
    assert not column.nullable, f"{table.name}.tenant_id が NULL を取れます"
    assert _points_at(column, "tenants.id"), f"{table.name}.tenant_id が tenants を指していません"


@pytest.mark.parametrize("table", [t for t in _TABLES if _kind(t) is Tenancy.PERSONAL], ids=lambda t: t.name)
def test_a_personal_table_follows_its_user(table: sa.Table) -> None:
    if table.name == "users":
        return
    column = table.columns.get("user_id")
    assert column is not None, f"{table.name} は利用者に付く表なのに user_id がありません"
    assert _points_at(column, "users.id"), f"{table.name}.user_id が users を指していません"


@pytest.mark.parametrize("table", [t for t in _TABLES if _kind(t) is not Tenancy.TENANT], ids=lambda t: t.name)
def test_only_tenant_tables_carry_a_tenant(table: sa.Table) -> None:
    """``tenant_id`` を持つのにテナントの表と宣言していないのは、宣言の誤り。

    （所属の表 ``user_tenants`` だけは、利用者に付く表として ``tenant_id`` を持つ。）
    """
    if table.name == "user_tenants":
        return
    assert "tenant_id" not in table.columns, f"{table.name} は tenant_id を持つのにテナントの表ではありません"
