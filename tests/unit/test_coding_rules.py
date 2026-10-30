"""CLAUDE.md の規則のうち、Ruff・MyPy では表せないものの機械的な検証（ADR-0089）。

規則を読んで守るのではなく、破ったら CI が落ちるようにする。例外は理由と一緒にこのファイルへ
書く（理由を書けないものは直す）。例外の表は、使われなくなったら別の試験が落とす。

層の依存方向は ``test_layer_dependencies.py``、設計の定量基準は ``test_design_metrics.py``、
文書と実物の突き合わせは ``test_documents_match.py``、API の認可は
``tests/integration/api/test_route_authorization.py``。
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from shared.domain.auth import master_data

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 検査対象。テストは時刻や環境変数を自由に扱うので含めない。
_SOURCE_ROOTS = ("asgi.py", "main.py", "bounded_contexts", "migrations", "presentation", "scripts", "shared")

#: 時刻の生成口（CLAUDE.md「時刻の契約」）
_TIME_ENTRANCE = "shared/kernel/timestamps.py"

#: 環境変数を直に読んでよいファイルと理由（CLAUDE.md「設定管理」）
_ENVIRONMENT_READERS: dict[str, str] = {
    "shared/kernel/settings/settings.py": "環境変数を読む正本",
    "presentation/fastapi/services/system_setting_service.py": "設定の画面に「環境変数で決まっている値」を出す",
    "shared/kernel/version.py": "ビルド情報と APP_ENV。画面や DB から変えられては困る（本番の判定に使う）",
    "shared/kernel/restart/terminator.py": "SERVER_SOFTWARE は gunicorn がプロセスに置く値で、設定ではない",
    "scripts/seed_master_data.py": "手で流す道具の入力",
    "scripts/create_system_admin.py": "手で流す道具の入力（パスワードを引数に書かせない）",
    "migrations/versions/0002_seed_master_data.py": "据え付けの入力（設定の表がまだ無い）",
}

#: ``getattr`` を使ってよいファイルと理由（CLAUDE.md「動的呼び出しの制限」）
_ATTRIBUTE_READERS: dict[str, str] = {
    "shared/kernel/logging/db_log_handler.py": "LogRecord の extra は標準ライブラリの作りで属性としてしか読めない",
    "shared/kernel/logging/logging_config.py": "標準ライブラリのログレベル名を引く",
    "shared/kernel/settings/settings.py": "threading.local の値は初回に属性が無い",
    "bounded_contexts/account_security/infrastructure/py_webauthn_relying_party.py": "webauthn の enum か文字列か",
}

_FORBIDDEN_DYNAMIC_CALLS = frozenset({"setattr", "delattr", "eval", "exec", "globals", "locals", "vars", "__import__"})

_VAGUE_MODULE = re.compile(r"(^|_)(utils?|helpers?)(_|$)")
_VAGUE_CLASS = re.compile(r"(Utils?|Helpers?)$")


def _sources() -> Iterator[tuple[str, ast.Module]]:
    for root in _SOURCE_ROOTS:
        path = _PROJECT_ROOT / root
        files = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for file in files:
            if "__pycache__" not in file.parts:
                yield file.relative_to(_PROJECT_ROOT).as_posix(), ast.parse(file.read_text(encoding="utf-8"))


def _calls(tree: ast.Module) -> Iterator[ast.Call]:
    return (node for node in ast.walk(tree) if isinstance(node, ast.Call))


def _clock_reads(tree: ast.Module) -> Iterator[int]:
    for call in _calls(tree):
        name = ast.unparse(call.func)
        if name.endswith(("datetime.now", "datetime.utcnow", "date.today")):
            yield call.lineno


def _reads_environment(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and ast.unparse(node) in {"os.environ", "os.getenv"}:
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "os"
            and {a.name for a in node.names} & {"environ", "getenv"}
        ):
            return True
    return False


def _called_names(tree: ast.Module) -> set[str]:
    return {call.func.id for call in _calls(tree) if isinstance(call.func, ast.Name)}


def test_time_comes_from_the_one_entrance() -> None:
    """``datetime.now()`` などは tz の有無が混ざる元になる。生成口を通す（CLAUDE.md「時刻の契約」）。"""
    found = [f"{path}:{line}" for path, tree in _sources() if path != _TIME_ENTRANCE for line in _clock_reads(tree)]
    assert not found, f"shared/kernel/timestamps.py の utcnow / utcnow_aware を使ってください: {found}"


def test_settings_are_read_through_the_settings_object() -> None:
    found = [path for path, tree in _sources() if _reads_environment(tree) and path not in _ENVIRONMENT_READERS]
    assert not found, f"環境変数は settings の @property から読んでください（要るなら理由を例外に）: {found}"


def test_no_dynamic_dispatch() -> None:
    found = [f"{path}: {name}" for path, tree in _sources() for name in _called_names(tree) & _FORBIDDEN_DYNAMIC_CALLS]
    assert not found, f"動的呼び出しは使えません（CLAUDE.md「動的呼び出しの制限」）: {found}"


def test_getattr_only_where_a_reason_is_written() -> None:
    found = [path for path, tree in _sources() if "getattr" in _called_names(tree) and path not in _ATTRIBUTE_READERS]
    assert not found, f"getattr を使わず明示的なインターフェースにしてください: {found}"


@pytest.mark.parametrize(
    ("exemptions", "still_applies"),
    [
        (_ENVIRONMENT_READERS, _reads_environment),
        (_ATTRIBUTE_READERS, lambda tree: "getattr" in _called_names(tree)),
    ],
    ids=["environment", "getattr"],
)
def test_exemptions_are_still_needed(exemptions: dict[str, str], still_applies: object) -> None:
    """直したのに例外だけ残ると、そのファイルで規則が効かないままになる。"""
    assert callable(still_applies)
    trees = dict(_sources())
    stale = [path for path in exemptions if path not in trees or not still_applies(trees[path])]
    assert not stale, f"もう要らない例外です。表から消してください: {stale}"


def _native_enums(tree: ast.Module) -> Iterator[int]:
    for call in _calls(tree):
        if ast.unparse(call.func) not in {"sa.Enum", "sqlalchemy.Enum"}:
            continue
        chosen = {kw.arg: kw.value for kw in call.keywords}.get("native_enum")
        if not (isinstance(chosen, ast.Constant) and chosen.value is False):
            yield call.lineno


def test_no_native_enum_columns() -> None:
    found = [f"{path}:{line}" for path, tree in _sources() for line in _native_enums(tree)]
    assert not found, f"sa.Enum には native_enum=False を付けてください（CLAUDE.md「DB モデリング」）: {found}"


def _migrations() -> Iterator[tuple[str, ast.Module]]:
    return ((path, tree) for path, tree in _sources() if path.startswith("migrations/versions/"))


def test_migrations_start_with_future_annotations() -> None:
    def has_it(tree: ast.Module) -> bool:
        return any(isinstance(n, ast.ImportFrom) and n.module == "__future__" for n in tree.body)

    found = [path for path, tree in _migrations() if not has_it(tree)]
    assert not found, f"from __future__ import annotations がありません: {found}"


def test_migrations_can_go_both_ways() -> None:
    def functions(tree: ast.Module) -> set[str]:
        return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}

    found = [path for path, tree in _migrations() if not {"upgrade", "downgrade"} <= functions(tree)]
    assert not found, f"upgrade() と downgrade() の両方が要ります: {found}"


def test_no_vague_names() -> None:
    modules = [path for path, _ in _sources() if _VAGUE_MODULE.search(Path(path).stem)]
    classes = [
        f"{path}: {node.name}"
        for path, tree in _sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and _VAGUE_CLASS.search(node.name)
    ]
    assert not modules + classes, f"util / helper という名前は使えません（ドメインの語で）: {modules + classes}"


def _schema_classes(tree: ast.Module) -> Iterator[str]:
    """``BaseModel`` を（同じファイルの中の継承も辿って）受け継ぐクラスの名前。"""
    known = {"BaseModel"}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and {ast.unparse(base) for base in node.bases} & known:
            known.add(node.name)
            yield node.name


def test_schemas_are_named_request_or_response() -> None:
    found = [
        f"{path}: {name}"
        for path, tree in _sources()
        if "presentation" in Path(path).parts
        for name in _schema_classes(tree)
        if not name.endswith(("Request", "Response"))
    ]
    assert not found, f"スキーマは 〇〇Request / 〇〇Response と名付けます（CLAUDE.md「API 設計」）: {found}"


def _role_name_comparisons(tree: ast.Module) -> Iterator[int]:
    roles = {name for _, name in master_data.ROLES}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        constants = {
            leaf.value
            for side in (node.left, *node.comparators)
            for leaf in ast.walk(side)
            if isinstance(leaf, ast.Constant)
        }
        if constants & roles or "active_role" in ast.unparse(node):
            yield node.lineno


def test_authorization_does_not_branch_on_role_names() -> None:
    """認可は scope で決める。ロール名で分岐すると、ロールの中身を変えても効かなくなる。"""
    found = [
        f"{path}:{line}"
        for path, tree in _sources()
        # マイグレーションはその時点のロールの行を名前で探す（認可ではない）
        if not path.startswith("migrations/")
        for line in _role_name_comparisons(tree)
    ]
    assert not found, f"ロール名で分岐しないでください（require_permission の scope で）: {found}"
