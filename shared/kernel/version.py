"""ビルド・バージョン情報。

Docker ビルド時に ``scripts/generate_version.sh`` が ``shared/kernel/version.json``
を生成し、ここで読み込む。ローカル開発では環境変数フォールバックのみで動く。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_VERSION_FILE = Path(__file__).with_name("version.json")


@dataclass(frozen=True)
class BuildInfo:
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
        version=os.getenv("APP_VERSION", payload.get("version", "0.0.0-dev")),
        git_sha=os.getenv("GIT_SHA", payload.get("commit_hash", "dev")),
        branch=payload.get("branch", "unknown"),
        build_time=os.getenv("BUILD_TIME", payload.get("build_date", "unknown")),
        environment=os.getenv("APP_ENV", "development"),
    )


__all__ = ["BuildInfo", "load_build_info"]
