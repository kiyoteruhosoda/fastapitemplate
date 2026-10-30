"""利用者が渡した宛先の確かめ（ADR-0083）。名前の引きは差し替える（外へは引きに行かない）。"""

from __future__ import annotations

import ipaddress

import pytest

from shared.kernel.outbound_destination import (
    PUSH_SERVICE_HOST_SUFFIXES,
    DestinationRefusedError,
    IpAddress,
    Resolver,
    check_host_name,
    check_https_url,
    ensure_public_host,
)


def _resolver(*addresses: str) -> Resolver:
    def resolve(host: str, port: int) -> set[IpAddress]:
        return {ipaddress.ip_address(address) for address in addresses}

    return resolve


def _reason(url: str, allowed_host_suffixes: tuple[str, ...] | None = None) -> str:
    with pytest.raises(DestinationRefusedError) as caught:
        check_https_url(url, allowed_host_suffixes=allowed_host_suffixes)
    return caught.value.reason


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://example.com/x", "invalid_url"),
        ("ftp://example.com/x", "invalid_url"),
        ("https:///x", "invalid_url"),
        ("https://user:pass@example.com/x", "invalid_url"),
        ("https://example.com:not-a-port/x", "invalid_url"),
        ("https://example.com:8443/x", "port_not_allowed"),
        ("https://127.0.0.1/", "blocked_address"),
        ("https://10.10.2.11/", "blocked_address"),
        ("https://169.254.169.254/", "blocked_address"),
        ("https://[::1]/", "blocked_address"),
        ("https://[::ffff:192.168.1.1]/", "blocked_address"),
        ("https://db/", "blocked_address"),
        ("https://app./", "blocked_address"),
        ("https://front.fastapitemplate-stg.svc.cluster.local/", "blocked_address"),
        ("https://front.blobshare-prod.svc/", "blocked_address"),
        ("https://nas.local/", "blocked_address"),
        ("https://router.home.arpa/", "blocked_address"),
    ],
)
def test_inner_or_malformed_urls_are_refused(url: str, reason: str) -> None:
    assert _reason(url) == reason


def test_a_public_url_passes_the_shape_check() -> None:
    parts = check_https_url("https://huggingface.co/a/b/resolve/main/m.safetensors")
    assert parts.hostname == "huggingface.co"
    assert check_https_url("https://93.184.215.14/x").hostname == "93.184.215.14"


def test_only_the_allowed_hosts_pass_when_given() -> None:
    allowed = PUSH_SERVICE_HOST_SUFFIXES
    assert check_https_url("https://fcm.googleapis.com/fcm/send/x", allowed_host_suffixes=allowed)
    assert check_https_url("https://updates.push.services.mozilla.com/wpush/v2/x", allowed_host_suffixes=allowed)
    assert _reason("https://example.com/x", allowed_host_suffixes=allowed) == "host_not_allowed"
    assert _reason("https://fcm.googleapis.com.evil.example/x", allowed_host_suffixes=allowed) == "host_not_allowed"
    assert _reason("https://evilfcm.googleapis.com/x", allowed_host_suffixes=allowed) == "host_not_allowed"
    assert _reason("https://142.250.0.1/x", allowed_host_suffixes=allowed) == "host_not_allowed"


def test_a_name_with_any_inner_address_is_refused() -> None:
    ensure_public_host("example.com", resolve=_resolver("93.184.215.14"))
    for inner in ("10.43.0.10", "127.0.0.1", "192.168.1.5", "fd00::1", "224.0.0.1"):
        with pytest.raises(DestinationRefusedError) as caught:
            ensure_public_host("example.com", resolve=_resolver("93.184.215.14", inner))
        assert caught.value.reason == "blocked_address"


def test_a_name_that_does_not_resolve_is_refused() -> None:
    with pytest.raises(DestinationRefusedError) as caught:
        ensure_public_host("example.com", resolve=_resolver())
    assert caught.value.reason == "unresolvable"


def test_a_literal_address_is_checked_without_resolving() -> None:
    with pytest.raises(DestinationRefusedError):
        ensure_public_host("10.10.2.11")


@pytest.mark.parametrize("host", ["smtp.example.com", "EMAIL-SMTP.ap-northeast-1.amazonaws.com", "8.8.8.8"])
def test_host_name_outside_is_accepted(host: str) -> None:
    assert check_host_name(host) == host.lower()


@pytest.mark.parametrize(
    "host",
    [
        "10.10.2.11",
        "127.0.0.1",
        "[::1]",
        "db",
        "app.svc",
        "x.cluster.local",
        "smtp.local",
        "https://a.example",
        "a b.example",
        "",
    ],
)
def test_host_name_inside_or_malformed_is_refused(host: str) -> None:
    with pytest.raises(DestinationRefusedError):
        check_host_name(host)
