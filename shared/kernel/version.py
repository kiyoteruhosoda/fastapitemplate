"""アプリ自身の名前と、ビルド・バージョン情報。

Docker ビルド時に ``scripts/generate_version.sh`` が ``shared/kernel/version.json``
を生成し、ここで読み込む。ローカル開発では環境変数フォールバックのみで動く。

**名前の正本は ``pyproject.toml`` の ``[project].name``**（ADR-0031）。ここから
FastAPI の題と、外へ出るときに名乗る User-Agent が導かれる。テンプレートから
起こしたアプリは名前を変える約束なので、変えた時点でどちらも追随する。
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_VERSION_FILE = Path(__file__).with_name("version.json")

#: 名前の正本。``shared/kernel/`` から見てリポジトリの根。
_PYPROJECT_FILE = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: 名前が読めなかったときに名乗るもの。**テンプレート名を既定にしない**
#: （読めていないことに気付けなくなる）。
_FALLBACK_NAME = "app"


@lru_cache(maxsize=1)
def project_name() -> str:
    """このアプリ自身の名前（``pyproject.toml`` の ``[project].name``）。

    ⚠ **1 度読んだら覚える。** 名前はプロセスの一生のあいだ変わらないので、
    要求のたびにファイルを開く理由が無い。
    """
    try:
        with _PYPROJECT_FILE.open("rb") as handle:
            name = tomllib.load(handle)["project"]["name"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
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
