"""Migrations do not seat the initial administrator (mechanical check of ADR-0078 §3).

ADR-0078 §3 decided that "only the installing ``0002`` and the seeding script call
``ensure_default_admin``", but nothing enforced it except convention and review.
``tests/integration/test_master_data_seeder.py`` watches the **behaviour** of
``seed_master_data``, so a new migration that calls ``ensure_default_admin`` itself slips through.

What happens when this is broken has been observed: **a default administrator deleted during
operation comes back in production with the publicly known default password** (derived app
blobshare, 2026-09-02, about 24 minutes on the public site). This fails at the point a migration
is added, not after it has been applied.

Besides calling the function, **pulling out the default values and building the admin yourself**
is the same trap, so it is checked too. The values come from ``shared/domain/auth/master_data.py``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _PROJECT_ROOT / "migrations" / "versions"

# The only migration allowed to seat the initial administrator (installation; ADR-0078 §3).
_SEATING_IS_ALLOWED_IN = frozenset({"0002_seed_master_data.py"})

# Names that indicate "seating the initial administrator". Catches both calling
# ``ensure_default_admin`` and pulling out default values to build a ``User`` yourself.
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
    assert files, "No migrations found (check _VERSIONS)"
    return files


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names_of(node: ast.AST) -> Iterator[str]:
    """Names that a single node brings in.

    So that aliasing an ``import`` (``as``) cannot dodge the check, ``ImportFrom`` returns the
    **original name**, not the alias. Attribute references (``master_data.DEFAULT_ADMIN_EMAIL``)
    are caught by their last name too, so every route of bringing a name in gives the same result.
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
        pytest.skip("Installing migration: the only place ADR-0078 §3 allows the initial administrator")

    found = sorted(_referenced_names(_parse(path)) & _SEATING_NAMES)

    assert not found, (
        f"{path.name} tries to seat the initial administrator: {found}."
        " Migrations that add permissions or roles call only seed_master_data (ADR-0078 §3)."
        " Otherwise an administrator deleted during operation comes back with the default password."
    )


@pytest.mark.parametrize("name", sorted(_SEATING_IS_ALLOWED_IN))
def test_the_installing_migration_still_seats_the_default_admin(name: str) -> None:
    """The allow list does not match nothing.

    Prevents the allow list from lingering after a file is renamed or the installation logic moves,
    while **an administrator gets seated somewhere outside the check**.
    """
    path = _VERSIONS / name
    assert path.exists(), f"Allow-listed migration does not exist: {name}"
    assert "ensure_default_admin" in _referenced_names(_parse(path)), (
        f"{name} does not seat the initial administrator. If installation moved, update _SEATING_IS_ALLOWED_IN"
    )


# --- Verifying the check itself ---------------------------------------------------
# The two tests above confirm "there are no violations". If the check breaks it silently
# passes, so the way names are collected is tested as well.


@pytest.mark.parametrize(
    "source",
    [
        # Import directly and call
        "from shared.infrastructure.master_data_seeder import ensure_default_admin",
        # Import under an alias (the original name is checked, not the alias)
        "from shared.infrastructure.master_data_seeder import ensure_default_admin as seat",
        # Import the module and call via attribute
        "master_data_seeder.ensure_default_admin(session)",
        # Do not call the function; pull out default values and build it yourself
        "from shared.domain.auth.master_data import DEFAULT_ADMIN_PASSWORD_HASH",
        "user.password_hash = master_data.DEFAULT_ADMIN_PASSWORD_HASH",
    ],
)
def test_seating_the_admin_is_detected(source: str) -> None:
    assert _referenced_names(ast.parse(source)) & _SEATING_NAMES, source


@pytest.mark.parametrize(
    "source",
    [
        # Re-seeding that only adds roles and permissions may be called any number of times
        "from shared.infrastructure.master_data_seeder import seed_master_data",
        "seed_master_data(session)",
        "from shared.domain.auth import master_data",
    ],
)
def test_seeding_roles_and_permissions_is_not_flagged(source: str) -> None:
    assert not _referenced_names(ast.parse(source)) & _SEATING_NAMES, source
