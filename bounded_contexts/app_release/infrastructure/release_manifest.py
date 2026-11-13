"""Read ``latest.json`` from the distribution store (ADR-0081 §4).

It is written by the app release procedure (stage 4 of deploy-repo's ``bin/flutter-release.sh``)
and looks like this::

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

Only ``version`` and ``built_at`` are used. ⚠ ``build`` is **not the build number**
(it is a build-time + commit pair). The build number is after the ``+`` in ``version``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from bounded_contexts.app_release.domain.app_release import (
    AppRelease,
    AppReleaseUnavailableError,
)


def read_release_manifest(document: bytes) -> AppRelease:
    """Extract the release from ``latest.json`` contents. Raises :class:`AppReleaseUnavailableError` if unreadable."""
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
    """Build time. ``None`` when missing or unparsable (not needed for the release notice, so don't fail)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


__all__ = ["read_release_manifest"]
