"""利用者ごとに「このアプリが持っている認証の手段」を数える（ADR-0039）。

このコンテキストが答えるのは**自分が持っている分だけ**——二要素認証（TOTP）と
パスキー。パスワードは ``users`` の列なので shared 側、IdP 経由の入り口は
ID 連携コンテキストが答える。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.account_security.domain.repositories.local_factor_directory import (
    LocalFactorDirectory,
)
from bounded_contexts.account_security.domain.value_objects.local_factors import (
    LocalFactors,
)


@dataclass(frozen=True)
class CountLocalFactors:
    directory: LocalFactorDirectory

    def execute(self) -> dict[int, LocalFactors]:
        return self.directory.factors_by_user()


__all__ = ["CountLocalFactors"]
