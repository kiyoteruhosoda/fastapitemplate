"""マイグレーションが初期管理者を据えないこと（ADR-0024 の機械的な検証）。

ADR-0024 は「``ensure_default_admin`` を呼ぶのは据え付けの ``0002`` と投入
スクリプトだけ」と決めたが、それを守らせるものは規約とレビューしか無かった。
``tests/integration/test_master_data_seeder.py`` が見張るのは
``seed_master_data`` の**振る舞い**なので、新しいマイグレーションが
``ensure_default_admin`` を自分で呼べば素通りする。

破れたときに起きることは実測済みで、**運用の途中で消した既定の管理者が、
公開されている既定のパスワードのまま本番に復活する**（派生アプリ blobshare、
2026-09-02、公開サイトで約 24 分）。落ちるのはマイグレーションを追加した
時点であって、当てたあとではない。

関数の呼び出しだけでなく、**既定の値を直に持ち出して自前で作る**形も同じ
地雷なので併せて見る。値の出所は ``shared/domain/auth/master_data.py``。
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _PROJECT_ROOT / "migrations" / "versions"

# 初期管理者を据えてよい唯一のマイグレーション（据え付け。ADR-0024）。
_SEATING_IS_ALLOWED_IN = frozenset({"0002_seed_master_data.py"})

# 「初期管理者を据えている」ことを表す名前。``ensure_default_admin`` を呼ぶ形と、
# 既定の値を持ち出して自分で ``User`` を組み立てる形の両方を拾う。
_SEATING_NAMES = frozenset(
    {
        "ensure_default_admin",
        "DEFAULT_ADMIN_EMAIL",
        "DEFAULT_ADMIN_ID",
        "DEFAULT_ADMIN_PASSWORD",
        "DEFAULT_ADMIN_PASSWORD_HASH",
        "DEFAULT_ADMIN_ROLE",
        "DEFAULT_ADMIN_USERNAME",
    }
)


def _file_name(path: Path) -> str:
    return path.name


def _migration_files() -> list[Path]:
    files = sorted(path for path in _VERSIONS.glob("*.py") if path.name != "__init__.py")
    assert files, "マイグレーションが見つからない（_VERSIONS を確認）"
    return files


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names_of(node: ast.AST) -> Iterator[str]:
    """1 つのノードが持ち込む名前。

    ``import`` の別名付け（``as``）で検査をすり抜けないよう、``ImportFrom`` は
    別名ではなく**元の名前**を返す。属性参照（``master_data.DEFAULT_ADMIN_EMAIL``）も
    末尾の名前で拾うので、どの経路で持ち込んでも同じ結果になる。
    """
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Attribute):
        yield node.attr
    elif isinstance(node, ast.ImportFrom):
        yield from (alias.name for alias in node.names)


def _referenced_names(tree: ast.Module) -> set[str]:
    return {name for node in ast.walk(tree) for name in _names_of(node)}


@pytest.mark.parametrize("path", _migration_files(), ids=_file_name)
def test_migrations_do_not_seat_the_default_admin(path: Path) -> None:
    if path.name in _SEATING_IS_ALLOWED_IN:
        pytest.skip("据え付けのマイグレーション。ADR-0024 が初期管理者を許す唯一の場所")

    found = sorted(_referenced_names(_parse(path)) & _SEATING_NAMES)

    assert not found, (
        f"{path.name} が初期管理者を据えようとしている: {found}。"
        " 権限やロールを足すマイグレーションは seed_master_data だけを呼ぶ（ADR-0024）。"
        " 呼ぶと、運用の途中で消した管理者が既定のパスワードのまま復活する。"
    )


@pytest.mark.parametrize("name", sorted(_SEATING_IS_ALLOWED_IN))
def test_the_installing_migration_still_seats_the_default_admin(name: str) -> None:
    """許可リストが空振りしていないこと。

    ファイル名を変えたり据え付けの中身を移したりしたときに、許可リストだけが
    残って**検査対象から外れた場所で管理者が据えられる**のを防ぐ。
    """
    path = _VERSIONS / name
    assert path.exists(), f"許可リストのマイグレーションが無い: {name}"
    assert "ensure_default_admin" in _referenced_names(_parse(path)), (
        f"{name} が初期管理者を据えていない。据え付けの経路が移ったなら _SEATING_IS_ALLOWED_IN も直す"
    )


# --- 検査そのものの検証 -------------------------------------------------------
# 上の 2 つは「違反が無いこと」を確認する。検査側が壊れると黙って通ってしまうため、
# 名前の集め方にもテストを当てる。


@pytest.mark.parametrize(
    "source",
    [
        # 直接 import して呼ぶ
        "from shared.infrastructure.master_data_seeder import ensure_default_admin",
        # 別名を付けて import する（別名ではなく元の名前を見る）
        "from shared.infrastructure.master_data_seeder import ensure_default_admin as seat",
        # モジュールごと import して属性で呼ぶ
        "master_data_seeder.ensure_default_admin(session)",
        # 関数を呼ばず、既定の値を持ち出して自前で作る
        "from shared.domain.auth.master_data import DEFAULT_ADMIN_PASSWORD_HASH",
        "user.password_hash = master_data.DEFAULT_ADMIN_PASSWORD_HASH",
    ],
)
def test_seating_the_admin_is_detected(source: str) -> None:
    assert _referenced_names(ast.parse(source)) & _SEATING_NAMES, source


@pytest.mark.parametrize(
    "source",
    [
        # ロールと権限を足すだけの再投入は、何度呼んでも構わない
        "from shared.infrastructure.master_data_seeder import seed_master_data",
        "seed_master_data(session)",
        "from shared.domain.auth import master_data",
    ],
)
def test_seeding_roles_and_permissions_is_not_flagged(source: str) -> None:
    assert not _referenced_names(ast.parse(source)) & _SEATING_NAMES, source
