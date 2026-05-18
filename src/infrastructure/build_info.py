import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version


@dataclass(frozen=True)
class BuildInfo:
    version: str
    git_sha: str
    build_time: str
    environment: str


def load_build_info() -> BuildInfo:
    try:
        fallback = pkg_version("fastapitemplate")
    except PackageNotFoundError:
        fallback = "0.0.0"

    return BuildInfo(
        version=os.getenv("APP_VERSION", fallback),
        git_sha=os.getenv("GIT_SHA", "dev"),
        build_time=os.getenv("BUILD_TIME", "unknown"),
        environment=os.getenv("APP_ENV", "development"),
    )
