"""配布しているアプリの最新版を返す口（ADR-0048）。

``GET /api/app-release/latest`` —— スマホアプリが開いたとき・前面に戻ったときに
呼び、自分のビルド番号より新しければ画面の上に知らせを出す。

⚠ **scope は要求しない（認証だけ）。** 権限をまだ持たない利用者（ゲスト）でも
アプリは入っている。版の知らせを受け取れないと、権限が付いたときに古い版のまま
取り残される。返すのは版番号と取りに行く先だけで、利用者ごとの情報は含まない。

アプリは assay のトークンで叩くので、関門は :data:`AppOrWebPrincipalDep`（ADR-0045）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from bounded_contexts.app_release.application.latest_app_release import LatestAppReleaseQuery
from bounded_contexts.app_release.infrastructure.s3_latest_release_source import S3LatestReleaseSource
from bounded_contexts.app_release.presentation.schemas import (
    AppReleaseSchema,
    LatestAppReleaseResponse,
)
from bounded_contexts.identity_federation.presentation.app_bearer import AppOrWebPrincipalDep
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import isoformat_utc

router = APIRouter(prefix="/api/app-release", tags=["app-release"])

# 答えの覚えはプロセスで 1 つ持つ（リクエストごとに作ると毎回置き場へ行く）。
_query = LatestAppReleaseQuery(S3LatestReleaseSource.from_settings)


def get_latest_app_release_query() -> LatestAppReleaseQuery:
    return _query


@router.get("/latest", response_model=LatestAppReleaseResponse)
def latest_app_release(
    _principal: AppOrWebPrincipalDep,
    query: Annotated[LatestAppReleaseQuery, Depends(get_latest_app_release_query)],
) -> LatestAppReleaseResponse:
    """配布面が最新として指している版を返す（無ければ ``latest`` が ``null``）。

    ⚠ ``async def`` にしない。置き場の読みは同期（boto3）で最大数秒かかるので、
    イベントループの上で走らせると他のリクエストまで止まる。
    """
    release = query.execute()
    if release is None:
        return LatestAppReleaseResponse(latest=None)
    return LatestAppReleaseResponse(
        latest=AppReleaseSchema(
            version=release.version,
            build=release.build,
            download_url=settings.app_release_download_url or None,
            built_at=isoformat_utc(release.built_at) if release.built_at else None,
        )
    )


__all__ = ["get_latest_app_release_query", "router"]
