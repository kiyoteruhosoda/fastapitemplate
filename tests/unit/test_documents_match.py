"""Comparing documents with reality (ADR-0089). ER diagram: ``tests/integration/test_er_document.py``."""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DECISIONS = _PROJECT_ROOT / "docs" / "decisions"
_ADR_FILE = re.compile(r"^ADR-(\d{4})-.+\.md$")

#: ARGs allowed in the Dockerfile. Build info is not passed via ``--build-arg`` (CLAUDE.md "Build and deploy")
_ALLOWED_BUILD_ARGS = {"UV_VERSION", "APP_UID"}


def _adr_numbers() -> list[int]:
    return sorted(int(match[1]) for path in _DECISIONS.iterdir() if (match := _ADR_FILE.match(path.name)))


def _dockerfile_lines() -> list[str]:
    lines = (_PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if not line.strip().startswith("#")]


def test_adr_numbers_have_no_gaps() -> None:
    """Duplicate numbering is not visible from file names alone, so heading numbers are checked too (next test)."""
    numbers = _adr_numbers()
    assert numbers
    assert numbers == list(range(numbers[0], numbers[-1] + 1))


def test_adr_titles_carry_their_file_number() -> None:
    wrong = []
    for path in _DECISIONS.iterdir():
        match = _ADR_FILE.match(path.name)
        if match and not path.read_text(encoding="utf-8").startswith(f"# ADR-{match[1]}: "):
            wrong.append(path.name)
    assert not wrong


def test_every_adr_is_listed_in_the_index() -> None:
    index = (_DECISIONS / "README.md").read_text(encoding="utf-8")
    assert not [number for number in _adr_numbers() if f"[ADR-{number:04d}]" not in index]


def test_every_screen_route_is_in_the_screen_document() -> None:
    routes = re.findall(r'path="([^"]+)"', (_PROJECT_ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8"))
    assert "/admin/users" in routes  # if parsing changes and this comes back empty, the checks below pass trivially
    document = (_PROJECT_ROOT / "frontend/README.md").read_text(encoding="utf-8")
    assert not [route for route in routes if f"`{route}" not in document]


def test_the_dockerfile_takes_no_build_information() -> None:
    declared = {line.split()[1].split("=")[0] for line in _dockerfile_lines() if line.startswith("ARG ")}
    assert declared
    assert declared <= _ALLOWED_BUILD_ARGS, f"Build info goes through scripts/generate_version.sh: {declared}"


def test_the_dockerfile_copies_only_from_its_own_stages() -> None:
    """``COPY --from`` an external image makes the image build depend on that registry (uv is installed from PyPI)."""
    lines = _dockerfile_lines()
    stages = {line.split()[-1] for line in lines if line.startswith("FROM ") and " AS " in line}
    sources = set(re.findall(r"^COPY --from=(\S+)", "\n".join(lines), re.MULTILINE))
    assert sources
    assert sources <= stages, sources - stages
