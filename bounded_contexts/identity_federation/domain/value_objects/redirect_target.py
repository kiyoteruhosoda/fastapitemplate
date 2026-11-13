"""Screen to return to after login (an SPA route).

**Never return to an external URL.** ``?redirect_to=`` is a parameter an attacker can set
freely; used as is, it could send the user to another site right after login
(open redirect). Only absolute paths within our own site are accepted; anything else
silently falls back to the default entrance.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TARGET = "/"


@dataclass(frozen=True)
class RedirectTarget:
    path: str = DEFAULT_TARGET

    @classmethod
    def parse(cls, value: str | None) -> RedirectTarget:
        """Pass only safe routes. Anything undecidable goes to the default entrance.

        ``//example.com`` is a "scheme-relative URL" that leaves the site, so it is rejected.
        ``\\`` is treated as ``/`` by some browsers, so it is rejected as well.
        """
        candidate = (value or "").strip()
        if not candidate.startswith(DEFAULT_TARGET):
            return cls()
        if candidate.startswith(("//", "/\\")):
            return cls()
        return cls(candidate)


__all__ = ["DEFAULT_TARGET", "RedirectTarget"]
