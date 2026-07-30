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


def _layer_of(module: str) -> str | None:
    """*module* が属するレイヤーを返す。どの層にも属さなければ ``None``。

    ``presentation.fastapi.*`` のようにトップレベルが層名のものと、
    ``bounded_contexts.<context>.<layer>.*`` の双方を同じ規則で扱う。
    """
    for part in module.split("."):
        if part in _LAYERS:
            return part
    return None


def _imported_modules(tree: ast.Module) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        # 相対 import は同一パッケージ内。レイヤーをまたがないため対象外。
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


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
            for imported in _imported_modules(_parse(path))
            if imported.startswith(_SOURCE_ROOTS) and _layer_of(imported) in forbidden
        }
    )

    assert not violations, f"{module} は {layer} 層なので {sorted(forbidden)} へ依存できない: {violations}"


@pytest.mark.parametrize("path", _domain_files(), ids=_module_name)
def test_domain_does_not_depend_on_frameworks(path: Path) -> None:
    module = _module_name(path)

    violations = sorted(
        {imported for imported in _imported_modules(_parse(path)) if imported.split(".")[0] in _FORBIDDEN_IN_DOMAIN}
    )

    assert not violations, f"{module} は domain 層なのでフレームワーク・DB に依存できない: {violations}"
