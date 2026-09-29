"""``GET /api/app-release/latest`` の応答スキーマ（ADR-0048）。"""

from __future__ import annotations

from pydantic import BaseModel


class AppReleaseSchema(BaseModel):
    """配布面に最新として置かれている版。"""

    #: 人に見せる版（``1.53.0``）。
    version: str
    #: 新旧の比較に使う番号。端末は自分のビルド番号より大きければ知らせる。
    build: int
    #: 人がブラウザで開いて APK を取りに行く先。設定が空なら ``None``。
    download_url: str | None
    #: 焼いた時刻（UTC、末尾 ``Z``）。配布面が書いていなければ ``None``。
    built_at: str | None


class LatestAppReleaseResponse(BaseModel):
    """``latest`` が ``None`` なら、知らせることは無い。

    読む先が設定されていない・配布面が読めなかった、のどちらでも ``None``
    になる。端末から見て違いは無い（どちらも知らせない）。
    """

    latest: AppReleaseSchema | None


__all__ = ["AppReleaseSchema", "LatestAppReleaseResponse"]
