"""アプリから来た assay のアクセストークンを読む口（ADR-0081 §1）。"""

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

    def verify_id_token(self, issuer: str, id_token: str, client_ids: frozenset[str]) -> Mapping[str, Any]:
        """アプリが送った ID トークンの署名・発行者・宛先（``client_ids`` のどれか）・期限を確かめる（ADR-0103）。

        結び付けたトークン（``cnf.jkt``）ではこちらから userinfo を引けないので、初めて来た人の
        プロフィールはこちらから読む。合わなければ ``AppAccessTokenRejectedError``。
        """
        ...

    def userinfo(self, issuer: str, token: str) -> Mapping[str, Any]:
        """そのトークンで userinfo を引く。``sub`` が食い違う応答は空として返す。"""
        ...


__all__ = ["AppTokenGateway"]
