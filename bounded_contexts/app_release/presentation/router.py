"""Endpoint returning the latest release of the apps we distribute (ADR-0081 §4).

``GET /api/app-release/latest`` — the mobile app calls it when opened or brought to the
foreground, and shows a notice at the top of the screen if the release is newer than its own build.

⚠ **No scope is required (authentication only).** Users without permissions yet (guests)
still have the app installed. If they could not receive release notices, they would be left on
an old version once granted permissions. Only the version and download location are returned;
nothing per-user.

The app calls it with an assay token, so the gate is :data:`AppOrWebPrincipalDep` (ADR-0081 §1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from bounded_contexts.app_release.application.latest_app_release import LatestAppReleaseQuery
from bounded_contexts.app_release.infrastructure.s3_latest_release_source import S3LatestReleaseSource
from bounded_contexts.app_release.presentation.schemas import (
    AppReleaseResponse,
    LatestAppReleaseResponse,
)
from bounded_contexts.identity_federation.presentation.app_bearer import AppOrWebPrincipalDep
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import isoformat_utc

router = APIRouter(prefix="/api/app-release", tags=["app-release"])

# Keep one answer cache per process (creating it per request would hit the store every time).
_query = LatestAppReleaseQuery(S3LatestReleaseSource.from_settings)


def get_latest_app_release_query() -> LatestAppReleaseQuery:
    return _query


@router.get("/latest", response_model=LatestAppReleaseResponse)
def latest_app_release(
    _principal: AppOrWebPrincipalDep,
    query: Annotated[LatestAppReleaseQuery, Depends(get_latest_app_release_query)],
) -> LatestAppReleaseResponse:
    """Return the release the distribution store points to as latest (``latest`` is ``null`` if none).

    ⚠ Do not make this ``async def``. Reading the store is synchronous (boto3) and can take
    seconds; running it on the event loop would block other requests too.
    """
    release = query.execute()
    if release is None:
        return LatestAppReleaseResponse(latest=None)
    return LatestAppReleaseResponse(
        latest=AppReleaseResponse(
            version=release.version,
            build=release.build,
            download_url=settings.app_release_download_url or None,
            built_at=isoformat_utc(release.built_at) if release.built_at else None,
        )
    )


__all__ = ["get_latest_app_release_query", "router"]
