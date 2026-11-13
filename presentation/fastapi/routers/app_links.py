"""Android App Links verification file (ADR-0081 §1).

The app receives the assay login at ``https://<this host>/app/oauth2redirect``.
Android hands this redirect **to the app instead of the browser** only when this file confirms
the link between the host and the app.

⚠ **Its content is set only by environment variables** (``ANDROID_APP_PACKAGE`` /
``ANDROID_APP_CERT_FINGERPRINTS``). If it could be changed from the UI, someone could declare a
different app as the recipient of authorization codes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from shared.kernel.settings.settings import settings

router = APIRouter(tags=["app-links"])


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
async def assetlinks() -> list[dict[str, object]]:
    package = settings.android_app_package
    fingerprints = list(settings.android_app_cert_fingerprints)
    if not (package and fingerprints):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package,
                "sha256_cert_fingerprints": fingerprints,
            },
        }
    ]


__all__ = ["router"]
