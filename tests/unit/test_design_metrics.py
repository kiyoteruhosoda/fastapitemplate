"""設計品質の定量基準のうち、Ruff で表せないもの（CLAUDE.md「品質ゲート」）。

Ruff が見るもの（`pyproject.toml` の `select` と閾値。ADR-0012）::

    C901     循環複雑度 10 以下
    PLR0912  分岐 8 個以下
    PLR0913  引数 4 個以下（標準は 3。DI・キーワード専用引数も数えられるため）
    PLR0915  文 30 個以下（関数の長さ 30 行以下の代替）

ここで見るもの::

    ネスト深度   3 段以下
    クラスの長さ 200 行以下

どちらも対応する Ruff ルールが無い。行数ではなく構造を見る指標なので、
`test_layer_dependencies.py` と同じく AST を歩いて判定する。

閾値を超える箇所を見つけたら、まず分割する。分割がかえって読みにくくなる場合だけ
`_CLASS_LENGTH_EXEMPTIONS` に理由付きで加える（例外は増やさない。増えるときは
基準そのものを見直して ADR を追加する）。
"""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 検査対象。mypy の `files` と同じ範囲（テスト自身も対象にする）。
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

# ネストとして数える文（`if` / ループ / `with` / `try` / `match`）。
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

# クラスの長さの例外（キー: `<相対パス>:<クラス名>`、値: 理由）。
_CLASS_LENGTH_EXEMPTIONS: dict[str, str] = {
    "shared/kernel/settings/settings.py:ApplicationSettings": (
        "設定値の型付きアクセサ（@property）の集まりで、長さは設定キーの数に比例する。"
        "分割すると『設定は settings.py の @property 経由』という規約の出所が散る"
        "（CLAUDE.md「設定管理」）。"
    ),
}


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in _SOURCE_ROOTS:
        path = _PROJECT_ROOT / root
        files.extend([path] if path.is_file() else sorted(path.rglob("*.py")))
    assert files, "検査対象のソースが見つからない（_SOURCE_ROOTS を確認）"
    return files


def _relative(path: Path) -> str:
    return path.relative_to(_PROJECT_ROOT).as_posix()


def _nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """*node* の中の最大ネスト深度。入れ子の関数・クラスは別に数えるため辿らない。"""
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
    """ネストは 3 段以下（深いネストは分岐の抽出漏れのサイン）。"""
    too_deep = [
        f"{_relative(path)}:{node.lineno} {node.name}（{_nesting_depth(node)} 段）"
        for path, tree in _parsed_files()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _nesting_depth(node) > _MAX_NESTING_DEPTH
    ]
    assert not too_deep, f"ネストが {_MAX_NESTING_DEPTH} 段を超えている:\n  " + "\n  ".join(too_deep)


def test_classes_are_not_longer_than_the_standard() -> None:
    """クラスは 200 行以下（例外は _CLASS_LENGTH_EXEMPTIONS に理由付きで置く）。"""
    too_long = [
        f"{_relative(path)}:{node.lineno} {node.name}（{node.end_lineno or node.lineno} 行目まで）"
        for path, tree in _parsed_files()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and f"{_relative(path)}:{node.name}" not in _CLASS_LENGTH_EXEMPTIONS
        and (node.end_lineno or node.lineno) - node.lineno + 1 > _MAX_CLASS_LINES
    ]
    assert not too_long, f"クラスが {_MAX_CLASS_LINES} 行を超えている:\n  " + "\n  ".join(too_long)


def test_class_length_exemptions_still_exist() -> None:
    """例外に挙げたクラスが実在すること（消えた例外を残さない）。"""
    defined = {
        f"{_relative(path)}:{node.name}"
        for path, tree in _parsed_files()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    stale = sorted(set(_CLASS_LENGTH_EXEMPTIONS) - defined)
    assert not stale, f"存在しないクラスが例外に残っている: {stale}"
