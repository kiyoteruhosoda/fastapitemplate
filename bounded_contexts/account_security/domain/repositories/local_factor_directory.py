"""第二要素の棚卸しのインターフェース（実装は Infrastructure 層。ADR-0039）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.account_security.domain.value_objects.local_factors import (
    LocalFactors,
)


class LocalFactorDirectory(Protocol):
    def factors_by_user(self) -> dict[int, LocalFactors]:
        """利用者 ID → 第二要素。1 つも持たない利用者は載らない。

        ⚠ **全員分をまとめて返す。** 1 人ずつ引く形にすると、画面が利用者の数だけ
        問い合わせることになる。
        """

    def factors_of(self, user_id: int) -> LocalFactors:
        """1 人分だけ数える。**自分の設定画面のように、相手が 1 人と決まっている
        ときだけ使う**（一覧からは呼ばない）。
        """


__all__ = ["LocalFactorDirectory"]
