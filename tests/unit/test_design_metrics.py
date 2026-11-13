"""Quantitative design-quality standards that Ruff cannot express (CLAUDE.md "Quality gates").

Checked by Ruff (`select` and thresholds in `pyproject.toml`; ADR-0072 §4)::

    C901     cyclomatic complexity at most 10
    PLR0912  at most 8 branches
    PLR0913  at most 4 arguments (the standard is 3; DI and keyword-only arguments are counted too)
    PLR0915  at most 30 statements (stand-in for "functions at most 30 lines")

Checked here::

    nesting depth  at most 3 levels
    class length   at most 200 lines

Neither has a matching Ruff rule. They measure structure rather than line counts, so like
`test_layer_dependencies.py` they are judged by walking the AST.

When something exceeds a threshold, split it first. Only when splitting would make it harder to
read, add it to `_CLASS_LENGTH_EXEMPTIONS` with a reason (do not grow the exemptions; if they grow,
revisit the standard itself and add an ADR).
"""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Files checked. Same scope as mypy's `files` (the tests themselves included).
_SOURCE_ROOTS = (
    "asgi.py",
    "main.py",
    "bounded_contexts",
    "migrations",
    "presentation",
    "scripts",
    "shared",
    "tests",
)

_MAX_NESTING_DEPTH = 3
_MAX_CLASS_LINES = 200

# Statements counted as nesting (`if` / loops / `with` / `try` / `match`).
_NESTING_STATEMENTS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)

_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

# Class-length exemptions (key: `<relative path>:<class name>`, value: reason).
_CLASS_LENGTH_EXEMPTIONS: dict[str, str] = {
    "shared/kernel/settings/settings.py:ApplicationSettings": (
        "A collection of typed accessors (@property) for settings; its length grows with the number of keys. "
        "Splitting it would scatter the source of the rule 'settings go through settings.py @property' "
        "(CLAUDE.md 'Settings management')."
    ),
}


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in _SOURCE_ROOTS:
        path = _PROJECT_ROOT / root
        files.extend([path] if path.is_file() else sorted(path.rglob("*.py")))
    assert files, "No source files to check were found (check _SOURCE_ROOTS)"
    return files


def _relative(path: Path) -> str:
    return path.relative_to(_PROJECT_ROOT).as_posix()


def _nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """Maximum nesting depth inside *node*. Nested functions/classes are counted separately, so not followed."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _NESTING_STATEMENTS):
            deepest = max(deepest, _nesting_depth(child, depth + 1))
        elif not isinstance(child, _DEFINITIONS):
            deepest = max(deepest, _nesting_depth(child, depth))
    return deepest


def _parsed_files() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in _source_files()]


def test_functions_are_not_nested_deeper_than_the_standard() -> None:
    """Nesting is at most 3 levels (deep nesting is a sign of a branch that should be extracted)."""
    too_deep = [
        f"{_relative(path)}:{node.lineno} {node.name} ({_nesting_depth(node)} levels)"
        for path, tree in _parsed_files()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _nesting_depth(node) > _MAX_NESTING_DEPTH
    ]
    assert not too_deep, f"Nesting exceeds {_MAX_NESTING_DEPTH} levels:\n  " + "\n  ".join(too_deep)


def test_classes_are_not_longer_than_the_standard() -> None:
    """Classes are at most 200 lines (exemptions go in _CLASS_LENGTH_EXEMPTIONS with a reason)."""
    too_long = [
        f"{_relative(path)}:{node.lineno} {node.name} (up to line {node.end_lineno or node.lineno})"
        for path, tree in _parsed_files()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and f"{_relative(path)}:{node.name}" not in _CLASS_LENGTH_EXEMPTIONS
        and (node.end_lineno or node.lineno) - node.lineno + 1 > _MAX_CLASS_LINES
    ]
    assert not too_long, f"Class exceeds {_MAX_CLASS_LINES} lines:\n  " + "\n  ".join(too_long)


def test_class_length_exemptions_still_exist() -> None:
    """Exempted classes must exist (do not keep exemptions for classes that are gone)."""
    defined = {
        f"{_relative(path)}:{node.name}"
        for path, tree in _parsed_files()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    stale = sorted(set(_CLASS_LENGTH_EXEMPTIONS) - defined)
    assert not stale, f"Exemptions remain for classes that no longer exist: {stale}"
