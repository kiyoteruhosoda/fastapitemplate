"""Implementation that reads ``latest.json`` from the distribution store (Garage) (ADR-0081 §4).

Does not go to the store. Replaces ``boto3.client`` and checks the credentials passed and the location read.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from bounded_contexts.app_release.domain.app_release import AppReleaseUnavailableError
from bounded_contexts.app_release.infrastructure import s3_latest_release_source
from bounded_contexts.app_release.infrastructure.s3_latest_release_source import S3LatestReleaseSource

_SECRET = "garage-secret-for-tests"


class _Client:
    def __init__(self, body: bytes | Exception) -> None:
        self.body = body
        self.asked: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803 — boto3 argument names
        self.asked.append((Bucket, Key))
        if isinstance(self.body, Exception):
            raise self.body
        return {"Body": io.BytesIO(self.body)}


class _Boto3:
    """Stand-in for ``boto3.client``. Remembers the arguments it was created with."""

    def __init__(self, client: _Client) -> None:
        self.client_instance = client
        self.kwargs: dict[str, Any] = {}

    def client(self, service: str, **kwargs: Any) -> _Client:
        assert service == "s3"
        self.kwargs = kwargs
        return self.client_instance


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    path = tmp_path / "secret-access-key"
    path.write_text(_SECRET + "\n", encoding="utf-8")
    return path


def _source(secret_file: Path | str, **overrides: str) -> S3LatestReleaseSource:
    values = {
        "endpoint_url": "http://garage.blob-prod.svc.cluster.local:3900",
        "region": "garage",
        "bucket": "artifacts",
        "object_key": "photonestapp/latest.json",
        "access_key_id": "GKexample",
        "secret_access_key_file": str(secret_file),
    }
    values.update(overrides)
    return S3LatestReleaseSource(**values)


def _install(monkeypatch: pytest.MonkeyPatch, body: bytes | Exception) -> _Boto3:
    fake = _Boto3(_Client(body))
    monkeypatch.setattr(s3_latest_release_source, "boto3", fake)
    return fake


def test_reads_the_manifest_with_the_secret_from_the_file(monkeypatch: pytest.MonkeyPatch, secret_file: Path) -> None:
    fake = _install(monkeypatch, json.dumps({"version": "1.53.0+356"}).encode())

    release = _source(secret_file).fetch()

    assert release is not None
    assert (release.version, release.build) == ("1.53.0", 356)
    assert fake.client_instance.asked == [("artifacts", "photonestapp/latest.json")]
    assert fake.kwargs["endpoint_url"] == "http://garage.blob-prod.svc.cluster.local:3900"
    assert fake.kwargs["aws_access_key_id"] == "GKexample"
    # Passed with the trailing newline dropped (files often end with one).
    assert fake.kwargs["aws_secret_access_key"] == _SECRET
    # Garage cannot resolve the bucket name placed in the host name.
    assert fake.kwargs["config"].s3 == {"addressing_style": "path"}


@pytest.mark.parametrize(
    "missing",
    ["endpoint_url", "bucket", "object_key", "access_key_id", "secret_access_key_file"],
)
def test_anything_missing_means_the_feature_is_off(
    monkeypatch: pytest.MonkeyPatch, secret_file: Path, missing: str
) -> None:
    fake = _install(monkeypatch, b"{}")

    assert _source(secret_file, **{missing: ""}).fetch() is None
    # Does not go to the store.
    assert fake.client_instance.asked == []


def test_an_unreadable_secret_file_is_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The path is configured but unreadable: an anomaly operators should notice, so distinguish it from "unused"."""
    _install(monkeypatch, b"{}")

    with pytest.raises(AppReleaseUnavailableError, match="secret access key file"):
        _source(tmp_path / "missing").fetch()


def test_an_empty_secret_file_is_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install(monkeypatch, b"{}")
    empty = tmp_path / "empty"
    empty.write_text("\n", encoding="utf-8")

    with pytest.raises(AppReleaseUnavailableError, match="empty"):
        _source(empty).fetch()


@pytest.mark.parametrize(
    "failure",
    [
        EndpointConnectionError(endpoint_url="http://garage:3900"),
        ClientError({"Error": {"Code": "AccessDenied", "Message": "Forbidden"}}, "GetObject"),
        ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject"),
    ],
)
def test_a_store_failure_is_unavailable(monkeypatch: pytest.MonkeyPatch, secret_file: Path, failure: Exception) -> None:
    _install(monkeypatch, failure)

    with pytest.raises(AppReleaseUnavailableError) as raised:
        _source(secret_file).fetch()

    # Secrets do not appear in the exception text (= the record).
    assert _SECRET not in str(raised.value)


def test_an_oversized_object_is_refused(monkeypatch: pytest.MonkeyPatch, secret_file: Path) -> None:
    _install(monkeypatch, b" " * (64 * 1024 + 1))

    with pytest.raises(AppReleaseUnavailableError, match="too large"):
        _source(secret_file).fetch()
