"""このアプリ側が持っている第二要素（ADR-0039）。

⚠ **IdP 側の多要素とは別物である。** IdP で多要素を必須にしても、ここは掛からない
——認証系が 2 つあるとはそういうことで、棚卸しはその前提で読む。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalFactors:
    #: 二要素認証（TOTP）が**有効になっている**か（登録手続き中は数えない）。
    totp: bool = False
    #: 登録済みのパスキーの本数。
    passkeys: int = 0


__all__ = ["LocalFactors"]
