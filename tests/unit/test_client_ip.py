"""接続元 IP の判定（監査ログに残る値なので、詐称できる経路を作らない）。

``X-Forwarded-For`` は送信元が自由に付けられるヘッダーで、同梱の nginx が使う
``$proxy_add_x_forwarded_for`` は受け取った値の**後ろ**に実際の接続元を足す。
つまり左端は攻撃者が置いた値になり得る。信頼するのは ``TRUSTED_PROXY_HOPS`` で
宣言した段数だけ、という判定をここで固定する。
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from presentation.fastapi.middleware.request_logging import _client_ip
from shared.kernel.settings.settings import ApplicationSettings

_PEER = "10.0.0.9"

# 信頼するプロキシ段数を差し替えるフィクスチャの型
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
    """``TRUSTED_PROXY_HOPS`` を差し替えるためのフィクスチャ。"""

    def apply(hops: int) -> None:
        monkeypatch.setattr(
            "presentation.fastapi.middleware.request_logging.settings",
            ApplicationSettings(env={"TRUSTED_PROXY_HOPS": str(hops)}),
        )

    return apply


def test_ignores_the_forwarded_header_by_default(trusted_hops: TrustedHops) -> None:
    """既定（0 段）ではヘッダーを一切見ない。直接公開しても詐称されない。"""
    trusted_hops(0)

    assert _client_ip(_request("1.2.3.4")) == _PEER


def test_takes_the_address_appended_by_the_trusted_proxy(trusted_hops: TrustedHops) -> None:
    """1 段なら右端（プロキシが自分で足した値）を採る。左端の詐称値は無視する。"""
    trusted_hops(1)

    assert _client_ip(_request("1.2.3.4, 203.0.113.7")) == "203.0.113.7"


def test_counts_hops_from_the_right(trusted_hops: TrustedHops) -> None:
    """2 段構成では外側のプロキシが記録した値まで遡る。"""
    trusted_hops(2)

    assert _client_ip(_request("1.2.3.4, 203.0.113.7, 10.0.0.2")) == "203.0.113.7"


def test_falls_back_when_the_header_is_shorter_than_declared(trusted_hops: TrustedHops) -> None:
    """宣言した段数に足りない = 想定した経路を通っていない。ヘッダーを信じない。"""
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
