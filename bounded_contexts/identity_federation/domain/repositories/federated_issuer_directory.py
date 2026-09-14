"""結び付きの棚卸しのインターフェース（実装は Infrastructure 層。ADR-0039）。"""

from __future__ import annotations

from typing import Protocol


class FederatedIssuerDirectory(Protocol):
    def issuers_by_user(self) -> dict[int, tuple[str, ...]]:
        """利用者 ID → 結び付いている issuer の並び。無い利用者は載らない。

        ⚠ **全員分をまとめて返す。** 1 人ずつ引く形にすると、画面が利用者の数だけ
        問い合わせることになる。
        """


__all__ = ["FederatedIssuerDirectory"]
