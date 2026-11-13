"""Reading ``latest.json`` from the distribution store (ADR-0081 §4).

Its shape is what deploy-repo's ``bin/flutter-release.sh`` writes. ⚠ ``build`` is not the build
number (it is the pair of build time and commit). The number is after the ``+`` in ``version``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from bounded_contexts.app_release.domain.app_release import AppReleaseUnavailableError
from bounded_contexts.app_release.infrastructure.release_manifest import read_release_manifest


def _manifest(**overrides: object) -> bytes:
    document: dict[str, object] = {
        "app": "photonestapp",
        "version": "1.53.0+356",
        "commit": "abc1234",
        "build": "20260927T010203Z-abc1234",
        "apk": "photonestapp/20260927T010203Z-abc1234/photonestapp-1.53.0-arm64-v8a-release.apk",
        "apks": {"arm64-v8a": "photonestapp/20260927T010203Z-abc1234/photonestapp-1.53.0-arm64-v8a-release.apk"},
        "aab": "photonestapp/20260927T010203Z-abc1234/photonestapp-1.53.0-release.aab",
        "built_at": "2026-09-27T01:02:03Z",
    }
    document.update(overrides)
    return json.dumps(document).encode()


def test_reads_the_version_and_build_number() -> None:
    release = read_release_manifest(_manifest())

    assert release.version == "1.53.0"
    # Not the ``build`` field ("20260927T010203Z-abc1234") but after the + in the version.
    assert release.build == 356
    assert release.built_at == datetime(2026, 9, 27, 1, 2, 3, tzinfo=UTC)


def test_a_missing_or_odd_build_time_is_not_a_failure() -> None:
    """The build time is not needed for the notice. Even if it is unreadable, the version is announced."""
    assert read_release_manifest(_manifest(built_at=None)).built_at is None
    assert read_release_manifest(_manifest(built_at="yesterday")).built_at is None


def test_a_build_time_without_a_zone_is_read_as_utc() -> None:
    release = read_release_manifest(_manifest(built_at="2026-09-27T01:02:03"))

    assert release.built_at == datetime(2026, 9, 27, 1, 2, 3, tzinfo=UTC)


@pytest.mark.parametrize(
    "document",
    [
        b"not json",
        b"[]",
        _manifest(version=None),
        # A version without a build number cannot be compared as newer or older.
        _manifest(version="1.53.0"),
        _manifest(version="v1.53.0+356"),
    ],
)
def test_an_unreadable_manifest_is_unavailable(document: bytes) -> None:
    with pytest.raises(AppReleaseUnavailableError):
        read_release_manifest(document)
