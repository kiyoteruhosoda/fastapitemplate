"""The app's own name, and build/version information.

At Docker build time ``scripts/generate_version.sh`` generates ``shared/kernel/version.json``,
which is read here. In local development it runs on environment variable fallbacks only.

**The name's source of truth is ``[project].name`` in ``pyproject.toml``** (ADR-0073 §2). The
FastAPI title and the User-Agent used for outbound requests are derived from it. Apps created
from the template promise to change the name, and both follow as soon as it is changed.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_VERSION_FILE = Path(__file__).with_name("version.json")

#: Source of the name. The repository root as seen from ``shared/kernel/``.
_PYPROJECT_FILE = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: Name used when the name cannot be read. **Do not default to the template name**
#: (it would hide the fact that reading failed).
_FALLBACK_NAME = "app"


@lru_cache(maxsize=1)
def project_name() -> str:
    """This app's own name (``[project].name`` in ``pyproject.toml``).

    ⚠ **Remembered once read.** The name never changes during the process's lifetime, so there is
    no reason to open the file on every request.
    """
    try:
        with _PYPROJECT_FILE.open("rb") as handle:
            name = tomllib.load(handle)["project"]["name"]
    except OSError, KeyError, TypeError, tomllib.TOMLDecodeError:
        return _FALLBACK_NAME
    return str(name).strip() or _FALLBACK_NAME


@dataclass(frozen=True)
class BuildInfo:
    name: str
    version: str
    git_sha: str
    branch: str
    build_time: str
    environment: str


def load_build_info() -> BuildInfo:
    payload: dict[str, str] = {}
    if _VERSION_FILE.exists():
        try:
            payload = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
        except ValueError:
            payload = {}
    return BuildInfo(
        name=project_name(),
        version=os.getenv("APP_VERSION", payload.get("version", "0.0.0-dev")),
        git_sha=os.getenv("GIT_SHA", payload.get("commit_hash", "dev")),
        branch=payload.get("branch", "unknown"),
        build_time=os.getenv("BUILD_TIME", payload.get("build_date", "unknown")),
        environment=os.getenv("APP_ENV", "development"),
    )


__all__ = ["BuildInfo", "load_build_info", "project_name"]
