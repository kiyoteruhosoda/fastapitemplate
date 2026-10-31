"""名前の付け替えのスクリプト（ADR-0099）。リポジトリの写しの中で実際に流す。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = "scripts/rename_project.sh"
# [t] を挟む。付け替えの対象にならないように（スクリプトと同じ）
_OLD = "fastapi[t]emplate"
_NEW = "renamed-app"
_RECORDS = (":!docs/CHANGELOG.md", ":!docs/decisions")

pytestmark = pytest.mark.skipif(
    subprocess.run(["grep", "-q", _OLD, str(_ROOT / "pyproject.toml")], check=False).returncode != 0,
    reason="付け替え済みの派生アプリでは流さない",
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    """追跡しているファイルだけを写した、新しいリポジトリ。"""
    tracked = _git(_ROOT, "ls-files", "-z").stdout.split("\0")
    for name in filter(None, tracked):
        source = _ROOT / name
        if source.is_file():
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "copy")
    return tmp_path


def _rename(copy: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", _SCRIPT, *args], cwd=copy, capture_output=True, text=True, check=False)


def _left_over(copy: Path) -> str:
    return _git(copy, "grep", "-n", "-i", "-E", _OLD, "--", *_RECORDS).stdout


def test_no_name_is_left_and_the_records_are_kept(copy: Path) -> None:
    changelog = (copy / "docs/CHANGELOG.md").read_text(encoding="utf-8")

    result = _rename(copy, _NEW)

    assert result.returncode == 0, result.stderr
    assert _left_over(copy) == ""
    assert f'name = "{_NEW}"' in (copy / "pyproject.toml").read_text(encoding="utf-8")
    assert f'name = "{_NEW}"' in (copy / "uv.lock").read_text(encoding="utf-8")
    assert (copy / "docs/CHANGELOG.md").read_text(encoding="utf-8") == changelog
    assert "git.nolumia.com" in _git(copy, "remote", "get-url", "template").stdout


@pytest.mark.parametrize("name", ["", "MyApp", "my app", "my_app", "1app", "-app", "app-", "a--b", "a" * 41, "a/b"])
def test_a_bad_name_is_refused_and_nothing_changes(copy: Path, name: str) -> None:
    assert _rename(copy, name).returncode != 0
    assert _git(copy, "status", "--porcelain").stdout == ""


def test_the_template_name_is_refused(copy: Path) -> None:
    assert _rename(copy, "fastapi" + "template").returncode != 0


def test_uncommitted_changes_are_refused(copy: Path) -> None:
    (copy / "README.md").write_text("changed", encoding="utf-8")
    assert _rename(copy, _NEW).returncode != 0
    assert _git(copy, "diff", "--name-only").stdout.strip() == "README.md"


def test_a_renamed_copy_is_refused(copy: Path) -> None:
    assert _rename(copy, _NEW).returncode == 0
    _git(copy, "add", "-A")
    _git(copy, "commit", "-q", "-m", "renamed")
    assert _rename(copy, "other-app").returncode != 0
