"""Checks for when the server connects to a destination given by a user (ADR-0083).

Where **the server connects to a URL a user wrote** (Web Push endpoints, URLs of files to fetch),
it must not be pointed at the home network or the inside of the cluster (the DB, other apps, host
management endpoints) (SSRF). Checked in two steps.

1. :func:`check_https_url` -- looks at the shape only (no name lookup): https, port 443, no
   userinfo. Refuses internal names (one-word Service names like ``db``, ``.svc``, ``.local``
   etc.) and literal IPs that are not globally routable. With ``allowed_host_suffixes``, only
   those hosts (and their subdomains) are accepted.
2. :func:`ensure_public_host` -- resolves the name and refuses if **any** address is not globally
   routable (private, loopback, link-local, reserved, etc.). Call it right before connecting.
   When following redirects (3xx), redo 1 and 2 **for every redirect** (same as Scheduler's
   ``http_fetcher.py``).

⚠ Does not prevent the answer from changing between the lookup and the connection (DNS rebinding).
⚠ Never log the URL itself (a push endpoint URL alone is enough to claim the destination).
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from urllib.parse import SplitResult, urlsplit

#: Hosts of browser push services (exact match or a subdomain). Same as WBS's ``PUSH_SERVICE_HOST_SUFFIXES``.
#: Chrome / Edge (incl. Android) = FCM, Firefox = Mozilla, Edge (Windows) = WNS, Safari = Apple.
PUSH_SERVICE_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
    "push.apple.com",
)

#: Name suffixes that exist only on the inside. One-word names (``db``, ``app`` = Services in the
#: same namespace) are refused too.
INTERNAL_NAME_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".svc", ".cluster.local")

_HOST_NAME = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
#: Name -> addresses. Only tests replace it.
Resolver = Callable[[str, int], Iterable[IpAddress]]


class DestinationRefusedError(ValueError):
    """Destination refused. ``reason`` is one of ``invalid_url`` / ``host_not_allowed`` /
    ``port_not_allowed`` / ``blocked_address`` / ``unresolvable``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _literal_address(host: str) -> IpAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _is_public(address: IpAddress) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def _matches(host: str, suffixes: Iterable[str]) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def _check_host(host: str, allowed_host_suffixes: Iterable[str] | None) -> None:
    literal = _literal_address(host)
    if literal is not None:
        if allowed_host_suffixes is not None:
            raise DestinationRefusedError("host_not_allowed")
        if not _is_public(literal):
            raise DestinationRefusedError("blocked_address")
        return
    if allowed_host_suffixes is not None:
        if not _matches(host, allowed_host_suffixes):
            raise DestinationRefusedError("host_not_allowed")
        return
    if "." not in host or host.endswith(INTERNAL_NAME_SUFFIXES):
        raise DestinationRefusedError("blocked_address")


def check_https_url(url: str, *, allowed_host_suffixes: Iterable[str] | None = None) -> SplitResult:
    """Check the shape of a URL and return its parts (no name lookup)."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as error:
        raise DestinationRefusedError("invalid_url") from error
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() != "https" or not host or parts.username is not None or parts.password is not None:
        raise DestinationRefusedError("invalid_url")
    if port not in (None, 443):
        raise DestinationRefusedError("port_not_allowed")
    _check_host(host, allowed_host_suffixes)
    return parts


def check_host_name(host: str) -> str:
    """Check the shape of a setting that holds a host name rather than a URL (mail server etc.;
    no name lookup)."""
    name = host.strip().lower().rstrip(".")
    if not _HOST_NAME.fullmatch(name) and _literal_address(name) is None:
        raise DestinationRefusedError("invalid_url")
    _check_host(name, None)
    return name


def resolve_addresses(host: str, port: int) -> set[IpAddress]:
    """All addresses the name resolves to. ``unresolvable`` if it cannot be resolved."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as error:
        raise DestinationRefusedError("unresolvable") from error
    return {ipaddress.ip_address(info[4][0]) for info in infos}


def ensure_public_host(host: str, port: int = 443, *, resolve: Resolver = resolve_addresses) -> None:
    """Check that every address of the name is globally routable (``blocked_address`` if not)."""
    literal = _literal_address(host)
    addresses = {literal} if literal is not None else set(resolve(host, port))
    if not addresses:
        raise DestinationRefusedError("unresolvable")
    if not all(_is_public(address) for address in addresses):
        raise DestinationRefusedError("blocked_address")


__all__ = [
    "INTERNAL_NAME_SUFFIXES",
    "PUSH_SERVICE_HOST_SUFFIXES",
    "DestinationRefusedError",
    "IpAddress",
    "Resolver",
    "check_host_name",
    "check_https_url",
    "ensure_public_host",
    "resolve_addresses",
]
