"""アプリから来た assay のアクセストークンを読む口（ADR-0045）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class AppTokenGateway(Protocol):
    def verify_access_token(self, issuer: str, token: str) -> Mapping[str, Any]:
        """署名・``typ``・発行者・宛先（``{issuer}/userinfo``）・期限を確かめてクレームを返す。

        合わなければ ``AppAccessTokenRejectedError``、IdP に届かなければ
        ``IdentityProviderUnavailableError``。
        """
        ...

    def userinfo(self, issuer: str, token: str) -> Mapping[str, Any]:
        """そのトークンで userinfo を引く。``sub`` が食い違う応答は空として返す。"""
        ...


__all__ = ["AppTokenGateway"]
