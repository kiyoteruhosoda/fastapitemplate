"""アプリ自身の名前の出どころ（ADR-0031）。

**名前を直に書かない**という決めごとを、書いてしまったときに気付けるようにする。
テンプレートから起こしたアプリが別のアプリの名前で名乗り続けた実績がある。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from bounded_contexts.identity_federation.infrastructure.oidc_metadata import USER_AGENT
from shared.kernel.version import load_build_info, project_name

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _name_in_pyproject() -> str:
    with (_PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["name"])


def test_the_name_comes_from_pyproject() -> None:
    assert project_name() == _name_in_pyproject()


def test_build_info_carries_the_name() -> None:
    assert load_build_info().name == _name_in_pyproject()


def test_the_user_agent_names_this_app() -> None:
    """IdP へ出ていく要求は、このアプリの名前で名乗る。"""
    assert USER_AGENT.startswith(f"{_name_in_pyproject()}/")


def test_the_swagger_title_is_the_name() -> None:
    """Swagger の題も同じ出どころから来る（直書きに戻っていないこと）。"""
    from presentation.fastapi.app import create_app

    assert create_app().title == _name_in_pyproject()
