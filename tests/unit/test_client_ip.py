"""Determining the client IP (it is stored in audit logs, so no path may allow spoofing).

``X-Forwarded-For`` is a header the sender can set freely, and ``$proxy_add_x_forwarded_for`` used
by the bundled nginx appends the actual peer **after** the received value. So the leftmost entry
can be attacker-supplied. This pins the rule that only as many hops as declared in
``TRUSTED_PROXY_HOPS`` are trusted.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from presentation.fastapi.middleware.request_logging import _client_ip
from shared.kernel.settings.settings import ApplicationSettings

_PEER = "10.0.0.9"

# Type of the fixture that replaces the number of trusted proxy hops
TrustedHops = Callable[[int], None]


def _request(forwarded_for: str | None) -> Request:
    headers = {} if forwarded_for is None else {"x-forwarded-for": forwarded_for}
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": Headers(headers).raw,
            "client": (_PEER, 12345),
        }
    )


@pytest.fixture
def trusted_hops(monkeypatch: pytest.MonkeyPatch) -> TrustedHops:
    """Fixture for replacing ``TRUSTED_PROXY_HOPS``."""

    def apply(hops: int) -> None:
        monkeypatch.setattr(
            "presentation.fastapi.middleware.request_logging.settings",
            ApplicationSettings(env={"TRUSTED_PROXY_HOPS": str(hops)}),
        )

    return apply


def test_ignores_the_forwarded_header_by_default(trusted_hops: TrustedHops) -> None:
    """By default (0 hops) the header is ignored entirely. Exposed directly, it cannot be spoofed."""
    trusted_hops(0)

    assert _client_ip(_request("1.2.3.4")) == _PEER


def test_takes_the_address_appended_by_the_trusted_proxy(trusted_hops: TrustedHops) -> None:
    """With 1 hop, take the rightmost value (added by the proxy itself). Spoofed leftmost values are ignored."""
    trusted_hops(1)

    assert _client_ip(_request("1.2.3.4, 203.0.113.7")) == "203.0.113.7"


def test_counts_hops_from_the_right(trusted_hops: TrustedHops) -> None:
    """With 2 hops, go back to the value recorded by the outer proxy."""
    trusted_hops(2)

    assert _client_ip(_request("1.2.3.4, 203.0.113.7, 10.0.0.2")) == "203.0.113.7"


def test_falls_back_when_the_header_is_shorter_than_declared(trusted_hops: TrustedHops) -> None:
    """Fewer entries than the declared hops = the expected path was not taken. Do not trust the header."""
    trusted_hops(2)

    assert _client_ip(_request("203.0.113.7")) == _PEER


def test_falls_back_when_the_header_is_absent(trusted_hops: TrustedHops) -> None:
    trusted_hops(1)

    assert _client_ip(_request(None)) == _PEER


def test_ignores_blank_entries(trusted_hops: TrustedHops) -> None:
    trusted_hops(1)

    assert _client_ip(_request("1.2.3.4, , 203.0.113.7")) == "203.0.113.7"


def test_negative_hop_counts_are_treated_as_untrusted() -> None:
    assert ApplicationSettings(env={"TRUSTED_PROXY_HOPS": "-1"}).trusted_proxy_hops == 0
