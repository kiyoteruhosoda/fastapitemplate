"""文書と実物の突き合わせ（ADR-0089）。ER 図の突き合わせは ``tests/integration/test_er_document.py``。"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DECISIONS = _PROJECT_ROOT / "docs" / "decisions"
_ADR_FILE = re.compile(r"^ADR-(\d{4})-.+\.md$")

#: Dockerfile の ARG に許すもの。ビルド情報は ``--build-arg`` で渡さない（CLAUDE.md「ビルドとデプロイ」）
_ALLOWED_BUILD_ARGS = {"UV_VERSION", "APP_UID"}


def _adr_numbers() -> list[int]:
    return sorted(int(match[1]) for path in _DECISIONS.iterdir() if (match := _ADR_FILE.match(path.name)))


def _dockerfile_lines() -> list[str]:
    lines = (_PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if not line.strip().startswith("#")]


def test_adr_numbers_have_no_gaps() -> None:
    """採番の重複はファイル名だけでは見えないので、見出しの番号も見る（次の試験）。"""
    numbers = _adr_numbers()
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
    document = (_PROJECT_ROOT / "frontend/README.md").read_text(encoding="utf-8")
    assert not [route for route in routes if f"`{route}" not in document]


def test_the_dockerfile_takes_no_build_information() -> None:
    declared = {line.split()[1].split("=")[0] for line in _dockerfile_lines() if line.startswith("ARG ")}
    assert declared <= _ALLOWED_BUILD_ARGS, f"ビルド情報は scripts/generate_version.sh で: {declared}"


def test_the_dockerfile_copies_only_from_its_own_stages() -> None:
    """外の像から ``COPY --from`` すると、像のビルドがその置き場に頼る（uv は PyPI から入れる）。"""
    lines = _dockerfile_lines()
    stages = {line.split()[-1] for line in lines if line.startswith("FROM ") and " AS " in line}
    sources = set(re.findall(r"^COPY --from=(\S+)", "\n".join(lines), re.MULTILINE))
    assert sources <= stages, sources - stages
