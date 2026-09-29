"""配布面の ``latest.json`` を読む（ADR-0048）。

書き手はアプリの配布手順（deploy-repo の ``bin/flutter-release.sh`` の stage 4）で、
次の形をしている::

    {
      "app": "photonestapp",
      "version": "1.53.0+356",
      "commit": "…",
      "build": "20260927T010203Z-abc1234",
      "apk": "photonestapp/…/photonestapp-1.53.0-arm64-v8a-release.apk",
      "apks": {"arm64-v8a": "…"},
      "aab": "…",
      "built_at": "2026-09-27T01:02:03Z"
    }

使うのは ``version`` と ``built_at`` だけ。⚠ ``build`` は**ビルド番号ではない**
（焼いた時刻とコミットの組）。ビルド番号は ``version`` の ``+`` の後ろにある。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from bounded_contexts.app_release.domain.app_release import (
    AppRelease,
    AppReleaseUnavailableError,
)


def read_release_manifest(document: bytes) -> AppRelease:
    """``latest.json`` の中身から版を取り出す。読めなければ :class:`AppReleaseUnavailableError`。"""
    try:
        data = json.loads(document)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppReleaseUnavailableError("latest.json is not valid JSON") from exc
    if not isinstance(data, dict):
        raise AppReleaseUnavailableError("latest.json is not a JSON object")

    version = data.get("version")
    if not isinstance(version, str):
        raise AppReleaseUnavailableError("latest.json carries no version")
    return AppRelease.from_pubspec_version(version, built_at=_built_at(data.get("built_at")))


def _built_at(value: object) -> datetime | None:
    """焼いた時刻。無い・読めないときは ``None``（版の知らせには要らないので落とさない）。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


__all__ = ["read_release_manifest"]
