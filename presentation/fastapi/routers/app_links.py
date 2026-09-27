"""Android App Links の検証ファイル（ADR-0045）。

アプリは assay でのログインを ``https://<このホスト>/app/oauth2redirect`` で受け取る。
Android がこの戻り先を**ブラウザではなくアプリへ**渡すのは、このファイルでホストと
アプリの結び付きを確かめられたときだけである。

⚠ **中身は環境変数だけで決める**（``ANDROID_APP_PACKAGE`` / ``ANDROID_APP_CERT_FINGERPRINTS``）。
画面から変えられると、別のアプリに認可コードを渡す宣言を書けてしまう。
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
