"""Where the app's own name comes from (ADR-0073 §2).

Makes it noticeable when someone breaks the rule **do not hard-code the name**. An app created
from the template has in fact kept introducing itself under another app's name.
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
    """Requests to the IdP identify themselves with this app's name."""
    assert USER_AGENT.startswith(f"{_name_in_pyproject()}/")


def test_the_swagger_title_is_the_name() -> None:
    """The Swagger title comes from the same source (has not reverted to a hard-coded name)."""
    from presentation.fastapi.app import create_app

    assert create_app().title == _name_in_pyproject()
