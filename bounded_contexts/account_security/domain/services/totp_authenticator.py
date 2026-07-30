"""TOTP の生成・検証インターフェース（実装は Infrastructure 層）。

RFC 6238 の計算そのものはライブラリに任せる。ドメインが知るのは
「共有鍵を作る」「認証アプリへ渡す URI を組み立てる」「コードを検証する」の 3 つ。
"""

from __future__ import annotations

from typing import Protocol


class TotpAuthenticator(Protocol):
    def generate_secret(self) -> str:
        """新しい共有鍵（Base32）を発行する。"""

    def provisioning_uri(self, *, secret: str, account_name: str) -> str:
        """認証アプリが読み取る ``otpauth://`` URI を組み立てる。"""

    def verify(self, *, secret: str, code: str) -> bool:
        """ワンタイムコードが正しいか判定する（時刻ずれの許容幅は実装側の設定）。"""


__all__ = ["TotpAuthenticator"]
