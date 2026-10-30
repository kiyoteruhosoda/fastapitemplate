"""利用者が渡した宛先へサーバーがつなぐときの確かめ（ADR-0083）。

Web Push の送り先や、取りに行くファイルの URL のように、**利用者が書いた URL へサーバーが
つなぎに行く**ところでは、宅内やクラスタの内側（DB・ほかのアプリ・ホストの管理の口）へ
向けさせない（SSRF）。2 段で確かめる。

1. :func:`check_https_url` —— 形だけを見る（名前を引かない）。https・ポート 443・利用者情報なし。
   内側の名前（``db`` のような 1 語の Service 名・``.svc``・``.local`` など）と、全世界向けでない
   IP の直書きは断る。``allowed_host_suffixes`` を渡すと、そのホスト（とその下）だけ受け取る。
2. :func:`ensure_public_host` —— 名前を引き、**どれか 1 つでも**全世界向けでないアドレス
   （私設・ループバック・リンクローカル・予約など）なら断る。つなぐ直前に呼ぶ。
   転送（3xx）を追うなら、**転送のたびに** 1 と 2 をやり直す（Scheduler の ``http_fetcher.py`` と同じ）。

⚠ 名前を引いてからつなぐまでの間に答えが変わる（DNS の付け替え）ことまでは防がない。
⚠ URL そのものはログに出さない（送り先の URL はそれだけで宛先を名乗れる）。
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import SplitResult, urlsplit

#: ブラウザの通知サービスのホスト（完全一致か、その下のホスト）。WBS の ``PUSH_SERVICE_HOST_SUFFIXES`` と同じ。
#: Chrome / Edge（Android 含む）= FCM、Firefox = Mozilla、Edge（Windows）= WNS、Safari = Apple。
PUSH_SERVICE_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
    "push.apple.com",
)

#: 内側にしか無い名前の末尾。1 語の名前（``db``・``app`` = 同じ namespace の Service）も断る。
INTERNAL_NAME_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".svc", ".cluster.local")

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
#: 名前 → アドレスの組。試験だけが差し替える。
Resolver = Callable[[str, int], Iterable[IpAddress]]


class DestinationRefusedError(ValueError):
    """宛先を断った。``reason`` は ``invalid_url`` / ``host_not_allowed`` / ``port_not_allowed`` /
    ``blocked_address`` / ``unresolvable`` のどれか。"""

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
    """URL の形を確かめて、分けたものを返す（名前は引かない）。"""
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


def resolve_addresses(host: str, port: int) -> set[IpAddress]:
    """名前を引いたアドレスの全部。引けなければ ``unresolvable``。"""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as error:
        raise DestinationRefusedError("unresolvable") from error
    return {ipaddress.ip_address(info[4][0]) for info in infos}


def ensure_public_host(host: str, port: int = 443, *, resolve: Resolver = resolve_addresses) -> None:
    """名前の全部のアドレスが全世界向けか確かめる（違えば ``blocked_address``）。"""
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
    "check_https_url",
    "ensure_public_host",
    "resolve_addresses",
]
