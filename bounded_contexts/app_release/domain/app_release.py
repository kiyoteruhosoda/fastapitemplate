"""A distributed release (ADR-0081 §4)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

#: Shape of ``version:`` in the app's ``pubspec.yaml`` (``1.53.0+356``).
#: The part after ``+`` is the build number, derived from the commit count of the app's
#: repository — releases are compared by it (it tells ``1.53.0`` apart from a rebuild of ``1.53.0``).
_PUBSPEC_VERSION = re.compile(r"^(?P<version>\d+\.\d+\.\d+)\+(?P<build>\d+)$")


class AppReleaseUnavailableError(Exception):
    """Could not read the latest release from the distribution store (store trouble, credentials, malformed data).

    ⚠ **Keep this distinct from "there is no latest release".** A missing setting just means the
    feature is not in use; this is an anomaly operations should notice. Both answer the device
    with "nothing to announce", but only this one is logged.
    """


@dataclass(frozen=True)
class AppRelease:
    """One release placed in the distribution store as latest."""

    #: Version shown to people (``1.53.0``).
    version: str
    #: Number used to compare releases (``356``). The device compares it with its own build number.
    build: int
    #: Build time (UTC). ``None`` if the distribution store does not record it.
    built_at: datetime | None

    @classmethod
    def from_pubspec_version(cls, value: str, *, built_at: datetime | None) -> AppRelease:
        """Build from the ``1.53.0+356`` form. Raises :class:`AppReleaseUnavailableError` on a bad shape."""
        match = _PUBSPEC_VERSION.match(value.strip())
        if match is None:
            raise AppReleaseUnavailableError(f"unrecognised release version: {value!r}")
        return cls(
            version=match.group("version"),
            build=int(match.group("build")),
            built_at=built_at,
        )


__all__ = ["AppRelease", "AppReleaseUnavailableError"]
