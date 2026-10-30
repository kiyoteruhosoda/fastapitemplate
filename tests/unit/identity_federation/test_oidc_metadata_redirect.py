"""OIDC の discovery と JWKS は転送を追わない（ADR-0090）。"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from bounded_contexts.identity_federation.domain.exceptions import IdentityProviderUnavailableError
from bounded_contexts.identity_federation.infrastructure.oidc_metadata import OidcMetadataCache


def test_a_redirect_from_the_issuer_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(kwargs)
        return httpx.Response(302, headers={"Location": "https://10.10.2.11/x"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(IdentityProviderUnavailableError):
        OidcMetadataCache()._fetch("https://idp.example.test/.well-known/openid-configuration")

    assert [call["follow_redirects"] for call in calls] == [False]
