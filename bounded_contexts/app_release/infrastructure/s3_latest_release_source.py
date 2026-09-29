"""配布面（S3 互換の置き場。Garage）から ``latest.json`` を読む（ADR-0048）。

⚠ **秘密の鍵は値ではなく場所で持つ。** 設定にあるのはファイルのパス
（``APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE``）だけで、中身は読むたびにファイルから
取る。設定の一覧・管理画面・バックアップに値が載らない。鍵を回したときも、
ファイルを差し替えれば次の読みから効く。

⚠ **鍵には ``artifacts`` の読み取りだけを持たせる。** 配布面には全アプリの成果物が
並んでいて、書ける鍵を渡すと、このサーバーが破られたときに配っている APK を
すり替えられる。
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

#: 置き場への接続・応答の待ち時間（秒）。端末は答えを待っているので、置き場が
#: 詰まっているときに長く待たせない。
_TIMEOUT_SECONDS = 3

#: ``latest.json`` は数百バイト。これを超えるものは読まずに断る。
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
        """読む先が揃っているか。1 つでも欠けていれば機能を使っていないとみなす。"""
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
            # パスは秘密ではないので出してよい（どこを直せばよいかが分かる）。
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
                # Garage はバケット名をホスト名に載せる形（virtual-hosted）を
                # 名前解決できない。パスに載せる。
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
