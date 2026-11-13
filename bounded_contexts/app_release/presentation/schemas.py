"""Response schema for ``GET /api/app-release/latest`` (ADR-0081 §4)."""

from __future__ import annotations

from pydantic import BaseModel


class AppReleaseResponse(BaseModel):
    """The release placed in the distribution store as latest."""

    #: Version shown to people (``1.53.0``).
    version: str
    #: Number used to compare releases. The device notifies if it is greater than its own build number.
    build: int
    #: Where people open a browser to get the APK. ``None`` when the setting is empty.
    download_url: str | None
    #: Build time (UTC, trailing ``Z``). ``None`` if the distribution store does not record it.
    built_at: str | None


class LatestAppReleaseResponse(BaseModel):
    """When ``latest`` is ``None`` there is nothing to announce.

    It is ``None`` both when nothing to read from is configured and when the distribution
    store could not be read. The device sees no difference (it announces nothing either way).
    """

    latest: AppReleaseResponse | None


__all__ = ["AppReleaseResponse", "LatestAppReleaseResponse"]
