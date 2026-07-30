"""レイヤー間の依存方向（CLAUDE.md「設計方針」の機械的な検証）。

許可する向き::

    Presentation → Application → Domain
    Infrastructure → Domain

禁止する向き（逆流）::

    Domain          → Application / Infrastructure / Presentation
    Application     → Infrastructure / Presentation
    Infrastructure  → Application / Presentation

``Presentation → Infrastructure`` は禁止しない。最も外側の層が具体実装を
組み立てて注入する（`Depends()` に渡す）のは Clean Architecture でも正しい
向きで、DI の配線をどこかで行う必要があるため。

Domain がフレームワークや DB に依存していないことも併せて確認する。ドメイン
ロジックを技術要素から切り離しておくための歯止めで、レビューに頼らず壊れた
時点で落とす。

相対 import（``from ...infrastructure import x``）も絶対名へ解決してから判定する。
ドットの数だけを見て「同一パッケージ内だから対象外」と扱うと、層をまたぐ相対
import が検査をすり抜ける。
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 検査対象のトップレベルパッケージ
_SOURCE_ROOTS = ("bounded_contexts", "shared", "presentation")

_LAYERS = ("domain", "application", "infrastructure", "presentation")

# レイヤーごとに import してはいけないレイヤー（依存の逆流）
_FORBIDDEN_LAYER_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset({"application", "infrastructure", "presentation"}),
    "application": frozenset({"infrastructure", "presentation"}),
    "infrastructure": frozenset({"application", "presentation"}),
    "presentation": frozenset(),
}

# Domain に持ち込ませない技術要素（フレームワーク・DB・Web）
_FORBIDDEN_IN_DOMAIN = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "pydantic",
    "werkzeug",
    "jwt",
    "pymysql",
)


def _iter_source_files() -> Iterator[Path]:
    for root in _SOURCE_ROOTS:
        for path in sorted((_PROJECT_ROOT / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _module_name(path: Path) -> str:
    relative = path.relative_to(_PROJECT_ROOT).with_suffix("")
    parts = tuple(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_of(path: Path) -> str:
    """相対 import の基点となるパッケージ名を返す。

    ``a/b/c.py`` なら ``a.b``、``a/b/__init__.py`` なら ``a.b``（``__init__.py``
    自身がパッケージ）。どちらもモジュール名から末尾を 1 つ落とした形になる。
    """
    relative = path.relative_to(_PROJECT_ROOT).with_suffix("")
    return ".".join(relative.parts[:-1])


def _resolve_relative_import(package: str, level: int, module: str | None) -> str | None:
    """相対 import を絶対モジュール名へ解決する。

    ``level`` は先頭のドットの数。``1`` が現在のパッケージ、``2`` 以上は 1 つずつ
    上へ辿る。パッケージの外へ出てしまう場合は ``None``（解決不能）。
    """
    parts = package.split(".") if package else []
    ascend = level - 1
    if ascend > len(parts):
        return None
    base = parts[: len(parts) - ascend] if ascend else parts
    if module:
        base = [*base, *module.split(".")]
    return ".".join(base) or None


def _layer_of(module: str) -> str | None:
    """*module* が属するレイヤーを返す。どの層にも属さなければ ``None``。

    ``presentation.fastapi.*`` のようにトップレベルが層名のものと、
    ``bounded_contexts.<context>.<layer>.*`` の双方を同じ規則で扱う。
    """
    for part in module.split("."):
        if part in _LAYERS:
            return part
    return None


def _imported_modules(tree: ast.Module, package: str) -> Iterator[str]:
    """*tree* が import しているモジュールを、すべて絶対名で返す。

    相対 import（``from ..infrastructure import x``）も *package* を基点に解決する。
    層をまたぐ相対 import があり得るため、ドットの数だけで対象外にはできない。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    yield node.module
            elif (resolved := _resolve_relative_import(package, node.level, node.module)) is not None:
                yield resolved


def _files_with_restricted_imports() -> list[Path]:
    """依存先を制限されている層（domain / application / infrastructure）のファイル。"""
    files = [
        path
        for path in _iter_source_files()
        if (layer := _layer_of(_module_name(path))) is not None and _FORBIDDEN_LAYER_IMPORTS[layer]
    ]
    assert files, "検査対象のソースが見つからない（_SOURCE_ROOTS を確認）"
    return files


def _domain_files() -> list[Path]:
    files = [path for path in _iter_source_files() if _layer_of(_module_name(path)) == "domain"]
    assert files, "domain 層のソースが見つからない（_SOURCE_ROOTS を確認）"
    return files


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("path", _files_with_restricted_imports(), ids=_module_name)
def test_layer_imports_do_not_flow_backwards(path: Path) -> None:
    module = _module_name(path)
    layer = _layer_of(module)
    assert layer is not None
    forbidden = _FORBIDDEN_LAYER_IMPORTS[layer]

    violations = sorted(
        {
            f"{imported} ({_layer_of(imported)})"
            for imported in _imported_modules(_parse(path), _package_of(path))
            if imported.startswith(_SOURCE_ROOTS) and _layer_of(imported) in forbidden
        }
    )

    assert not violations, f"{module} は {layer} 層なので {sorted(forbidden)} へ依存できない: {violations}"


@pytest.mark.parametrize("path", _domain_files(), ids=_module_name)
def test_domain_does_not_depend_on_frameworks(path: Path) -> None:
    module = _module_name(path)

    violations = sorted(
        {
            imported
            for imported in _imported_modules(_parse(path), _package_of(path))
            if imported.split(".")[0] in _FORBIDDEN_IN_DOMAIN
        }
    )

    assert not violations, f"{module} は domain 層なのでフレームワーク・DB に依存できない: {violations}"


# --- 検査そのものの検証 -------------------------------------------------------
# 上の 2 つは「違反が無いこと」を確認する。検査側が壊れると黙って通ってしまうため、
# 相対 import の解決と違反の検出そのものにもテストを当てる。


@pytest.mark.parametrize(
    ("package", "level", "module", "expected"),
    [
        # 同一パッケージ内（レイヤーをまたがない）
        ("bounded_contexts.example.domain.entities", 1, "item", "bounded_contexts.example.domain.entities.item"),
        ("bounded_contexts.example.domain.entities", 1, None, "bounded_contexts.example.domain.entities"),
        # 1 つ上へ: domain 内の別モジュール
        ("bounded_contexts.example.domain.entities", 2, "exceptions", "bounded_contexts.example.domain.exceptions"),
        # 2 つ上へ: 層をまたぐ（これを取りこぼすと検査が無意味になる）
        (
            "bounded_contexts.example.domain.entities",
            3,
            "infrastructure.item_model",
            "bounded_contexts.example.infrastructure.item_model",
        ),
        # パッケージの外へ出る相対 import は解決不能
        ("shared", 3, "x", None),
    ],
)
def test_relative_imports_resolve_to_absolute_names(
    package: str, level: int, module: str | None, expected: str | None
) -> None:
    assert _resolve_relative_import(package, level, module) == expected


def test_package_of_uses_the_containing_package() -> None:
    entities = _PROJECT_ROOT / "bounded_contexts" / "example" / "domain" / "entities"
    assert _package_of(entities / "item.py") == "bounded_contexts.example.domain.entities"
    # __init__.py 自身がパッケージなので、基点はその親ではなく自分
    assert _package_of(entities / "__init__.py") == "bounded_contexts.example.domain.entities"


@pytest.mark.parametrize(
    "source",
    [
        # 絶対 import
        "from bounded_contexts.example.infrastructure.item_model import ItemModel",
        "import bounded_contexts.example.infrastructure.item_model",
        # 相対 import（層をまたぐ）
        "from ...infrastructure.item_model import ItemModel",
        "from ...infrastructure import item_model",
    ],
)
def test_a_domain_module_reaching_infrastructure_is_detected(source: str) -> None:
    """domain → infrastructure を、絶対でも相対でも取りこぼさないこと。"""
    package = "bounded_contexts.example.domain.entities"
    imported = list(_imported_modules(ast.parse(source), package))

    assert any(_layer_of(name) == "infrastructure" for name in imported), imported
