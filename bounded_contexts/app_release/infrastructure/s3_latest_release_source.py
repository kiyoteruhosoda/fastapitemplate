"""Read ``latest.json`` from the distribution store (S3-compatible storage, Garage) (ADR-0081 §4).

⚠ **The secret key is held by location, not by value.** The settings hold only the file path
(``APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE``); the contents are read from the file on every read.
The value never appears in settings listings, the admin screen or backups. When the key is
rotated, replacing the file takes effect from the next read.

⚠ **Give the key read-only access to ``artifacts`` only.** The distribution store holds every
app's artifacts; with a writable key, a compromise of this server would let the distributed
APKs be swapped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from bounded_contexts.app_release.domain.app_release import (
    AppRelease,
    AppReleaseUnavailableError,
)
from bounded_contexts.app_release.infrastructure.release_manifest import read_release_manifest
from shared.kernel.settings.settings import settings

#: Connect/response timeout for the store (seconds). The device is waiting for the answer,
#: so don't keep it waiting long when the store is stuck.
_TIMEOUT_SECONDS = 3

#: ``latest.json`` is a few hundred bytes. Anything larger is refused without reading.
_MAX_MANIFEST_BYTES = 64 * 1024


@dataclass(frozen=True)
class S3LatestReleaseSource:
    endpoint_url: str
    region: str
    bucket: str
    object_key: str
    access_key_id: str
    secret_access_key_file: str

    @classmethod
    def from_settings(cls) -> S3LatestReleaseSource:
        return cls(
            endpoint_url=settings.app_release_s3_endpoint_url,
            region=settings.app_release_s3_region,
            bucket=settings.app_release_s3_bucket,
            object_key=settings.app_release_s3_object_key,
            access_key_id=settings.app_release_s3_access_key_id,
            secret_access_key_file=settings.app_release_s3_secret_access_key_file,
        )

    @property
    def configured(self) -> bool:
        """Whether everything to read from is set. If any is missing, the feature is treated as unused."""
        return all(
            (
                self.endpoint_url,
                self.bucket,
                self.object_key,
                self.access_key_id,
                self.secret_access_key_file,
            )
        )

    def fetch(self) -> AppRelease | None:
        if not self.configured:
            return None
        document = self._read_object(self._secret_access_key())
        return read_release_manifest(document)

    def _secret_access_key(self) -> str:
        try:
            secret = Path(self.secret_access_key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            # The path is not secret, so it is fine to include (it shows what to fix).
            raise AppReleaseUnavailableError(
                f"cannot read the secret access key file {self.secret_access_key_file}: {exc.strerror}"
            ) from exc
        if not secret:
            raise AppReleaseUnavailableError(f"the secret access key file {self.secret_access_key_file} is empty")
        return secret

    def _read_object(self, secret_access_key: str) -> bytes:
        client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region or None,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                # Garage cannot resolve the bucket name placed in the host name
                # (virtual-hosted style). Put it in the path.
                s3={"addressing_style": "path"},
                connect_timeout=_TIMEOUT_SECONDS,
                read_timeout=_TIMEOUT_SECONDS,
                retries={"max_attempts": 1},
            ),
        )
        try:
            response = client.get_object(Bucket=self.bucket, Key=self.object_key)
            body = response["Body"].read(_MAX_MANIFEST_BYTES + 1)
        except (BotoCoreError, ClientError) as exc:
            raise AppReleaseUnavailableError(
                f"cannot read s3://{self.bucket}/{self.object_key} from {self.endpoint_url}: {exc}"
            ) from exc
        if not isinstance(body, bytes):
            raise AppReleaseUnavailableError("the object body is not bytes")
        if len(body) > _MAX_MANIFEST_BYTES:
            raise AppReleaseUnavailableError(f"s3://{self.bucket}/{self.object_key} is too large to be latest.json")
        return body


__all__ = ["S3LatestReleaseSource"]
