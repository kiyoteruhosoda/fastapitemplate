"""認可要求を何のために始めたか（ADR-0040）。

IdP への往復は 2 つの目的で使う ——**入るため**（ログイン）と、**既に入っている
自分に結び付けるため**（連携）。戻り先の URI は 1 つしか登録しないので、
``/callback`` はこの値を見てどちらの後始末をするかを決める。

⚠ **目的は往復状態（署名付き Cookie）に入れる。** クエリに載せると、戻りの URL を
書き換えるだけで「ログインのつもりで始めた往復」を「連携」に化けさせられる。
"""

from __future__ import annotations

from enum import StrEnum


class TransactionPurpose(StrEnum):
    #: 入るための往復。戻りは引き換え券になる。
    LOGIN = "login"
    #: 既にログインしている利用者へ結び付けるための往復（ADR-0040）。
    LINK = "link"


__all__ = ["TransactionPurpose"]
