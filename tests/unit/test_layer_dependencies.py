"""Dependency direction between layers (mechanical check of CLAUDE.md "Design principles").

Allowed directions::

    Presentation → Application → Domain
    Infrastructure → Domain

Forbidden directions (backflow)::

    Domain          → Application / Infrastructure / Presentation
    Application     → Infrastructure / Presentation
    Infrastructure  → Application / Presentation

``Presentation → Infrastructure`` is not forbidden. The outermost layer assembling and injecting
concrete implementations (passing them to `Depends()`) is a correct direction in Clean Architecture
too, and the DI wiring has to happen somewhere.

It also checks that Domain does not depend on frameworks or the DB. This guard keeps domain logic
separate from technical concerns and fails as soon as it breaks, instead of relying on review.

Relative imports (``from ...infrastructure import x``) are resolved to absolute names before
judging. Looking only at the number of dots and treating it as "same package, out of scope"
would let relative imports across layers slip through.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Top-level packages checked
_SOURCE_ROOTS = ("bounded_contexts", "shared", "presentation")

_LAYERS = ("domain", "application", "infrastructure", "presentation")

# Layers that each layer must not import (dependency backflow)
_FORBIDDEN_LAYER_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset({"application", "infrastructure", "presentation"}),
    "application": frozenset({"infrastructure", "presentation"}),
    "infrastructure": frozenset({"application", "presentation"}),
    "presentation": frozenset(),
}

# Technical concerns Domain must not pull in (frameworks, DB, web)
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
    """Returns the package name used as the base for relative imports.

    ``a.b`` for ``a/b/c.py``, and ``a.b`` for ``a/b/__init__.py`` (``__init__.py`` is the package
    itself). Both are the module name with its last part dropped.
    """
    relative = path.relative_to(_PROJECT_ROOT).with_suffix("")
    return ".".join(relative.parts[:-1])


def _resolve_relative_import(package: str, level: int, module: str | None) -> str | None:
    """Resolves a relative import to an absolute module name.

    ``level`` is the number of leading dots. ``1`` is the current package; ``2`` and above go up one
    at a time. ``None`` (unresolvable) if it would leave the package.
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
    """Returns the layer *module* belongs to, or ``None`` if it belongs to none.

    Top-level layer names such as ``presentation.fastapi.*`` and
    ``bounded_contexts.<context>.<layer>.*`` are handled by the same rule.
    """
    for part in module.split("."):
        if part in _LAYERS:
            return part
    return None


def _imported_from(node: ast.ImportFrom, package: str) -> str | None:
    """Absolute name of the module ``from x import y`` points at, or ``None`` if unresolvable."""
    if node.level == 0:
        return node.module
    return _resolve_relative_import(package, node.level, node.module)


def _imported_modules(tree: ast.Module, package: str) -> Iterator[str]:
    """Returns every module *tree* imports, as absolute names.

    Relative imports (``from ..infrastructure import x``) are also resolved against *package*.
    Relative imports may cross layers, so they cannot be excluded by the number of dots alone.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and (resolved := _imported_from(node, package)) is not None:
            yield resolved


def _files_with_restricted_imports() -> list[Path]:
    """Files in layers whose dependencies are restricted (domain / application / infrastructure)."""
    files = [
        path
        for path in _iter_source_files()
        if (layer := _layer_of(_module_name(path))) is not None and _FORBIDDEN_LAYER_IMPORTS[layer]
    ]
    assert files, "No source files to check were found (check _SOURCE_ROOTS)"
    return files


def _domain_files() -> list[Path]:
    files = [path for path in _iter_source_files() if _layer_of(_module_name(path)) == "domain"]
    assert files, "No domain-layer source files found (check _SOURCE_ROOTS)"
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

    assert not violations, f"{module} is in the {layer} layer and cannot depend on {sorted(forbidden)}: {violations}"


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

    assert not violations, f"{module} is in the domain layer and cannot depend on frameworks or the DB: {violations}"


# --- Verifying the check itself ---------------------------------------------------
# The two tests above confirm "there are no violations". If the check breaks it silently
# passes, so relative-import resolution and violation detection are tested as well.


@pytest.mark.parametrize(
    ("package", "level", "module", "expected"),
    [
        # Within the same package (does not cross layers)
        ("bounded_contexts.example.domain.entities", 1, "item", "bounded_contexts.example.domain.entities.item"),
        ("bounded_contexts.example.domain.entities", 1, None, "bounded_contexts.example.domain.entities"),
        # One level up: another module within domain
        ("bounded_contexts.example.domain.entities", 2, "exceptions", "bounded_contexts.example.domain.exceptions"),
        # Two levels up: crosses layers (missing this would make the check meaningless)
        (
            "bounded_contexts.example.domain.entities",
            3,
            "infrastructure.item_model",
            "bounded_contexts.example.infrastructure.item_model",
        ),
        # A relative import that leaves the package cannot be resolved
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
    # __init__.py is the package itself, so the base is itself, not its parent
    assert _package_of(entities / "__init__.py") == "bounded_contexts.example.domain.entities"


@pytest.mark.parametrize(
    "source",
    [
        # Absolute import
        "from bounded_contexts.example.infrastructure.item_model import ItemModel",
        "import bounded_contexts.example.infrastructure.item_model",
        # Relative import (across layers)
        "from ...infrastructure.item_model import ItemModel",
        "from ...infrastructure import item_model",
    ],
)
def test_a_domain_module_reaching_infrastructure_is_detected(source: str) -> None:
    """domain -> infrastructure is caught whether absolute or relative."""
    package = "bounded_contexts.example.domain.entities"
    imported = list(_imported_modules(ast.parse(source), package))

    assert any(_layer_of(name) == "infrastructure" for name in imported), imported
