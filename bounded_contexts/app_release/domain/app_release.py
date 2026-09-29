"""配布している版（ADR-0048）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

#: アプリの ``pubspec.yaml`` の ``version:`` の形（``1.53.0+356``）。
#: ``+`` の後ろはビルド番号で、アプリのリポジトリのコミット数から振られる
#: ——版の新旧はこちらで比べる（``1.53.0`` と ``1.53.0`` の焼き直しを区別できる）。
_PUBSPEC_VERSION = re.compile(r"^(?P<version>\d+\.\d+\.\d+)\+(?P<build>\d+)$")


class AppReleaseUnavailableError(Exception):
    """配布面から最新版を読めなかった（置き場の不調・資格情報・書式の崩れ）。

    ⚠ **「最新版は無い」と区別する。** 設定が無いのは機能を使っていないだけで、
    こちらは運用で気付くべき異常。どちらも端末には「知らせることは無い」と返すが、
    こちらだけ記録に残す。
    """


@dataclass(frozen=True)
class AppRelease:
    """配布面に最新として置かれている 1 つの版。"""

    #: 人に見せる版（``1.53.0``）。
    version: str
    #: 新旧の比較に使う番号（``356``）。端末は自分のビルド番号と比べる。
    build: int
    #: 焼いた時刻（UTC）。配布面が書いていなければ ``None``。
    built_at: datetime | None

    @classmethod
    def from_pubspec_version(cls, value: str, *, built_at: datetime | None) -> AppRelease:
        """``1.53.0+356`` の形から作る。形が違えば :class:`AppReleaseUnavailableError`。"""
        match = _PUBSPEC_VERSION.match(value.strip())
        if match is None:
            raise AppReleaseUnavailableError(f"unrecognised release version: {value!r}")
        return cls(
            version=match.group("version"),
            build=int(match.group("build")),
            built_at=built_at,
        )


__all__ = ["AppRelease", "AppReleaseUnavailableError"]
