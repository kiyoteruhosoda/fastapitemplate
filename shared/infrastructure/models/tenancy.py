"""表ごとの「誰のものか」の宣言（ADR-0079 §1 決定 6・ADR-0079 §2）。

全部の表が、次の 3 つのどれかを ``info`` に宣言する。宣言の無い表と、宣言と列が
食い違う表は ``tests/integration/test_table_tenancy.py`` が落とす。

- :attr:`Tenancy.TENANT` —— テナントの中身。``tenant_id`` を持ち、読み書きは必ず主体の
  テナントで絞る（絞るのはリポジトリの入口）
- :attr:`Tenancy.PERSONAL` —— 利用者 1 人に付くもの。``user_id`` で利用者に従い、
  利用者を通してテナントが決まる（利用者そのもの ``users`` もここ）
- :attr:`Tenancy.GLOBAL` —— アプリ全体のもの（テナント・ロールの雛形・設定・アプリログ）

派生アプリが表を足すときも、どれかを宣言する。迷ったら ``TENANT``。
"""

from __future__ import annotations

from enum import StrEnum

TENANCY_KEY = "tenancy"


class Tenancy(StrEnum):
    TENANT = "tenant"
    PERSONAL = "personal"
    GLOBAL = "global"


def tenancy_info(kind: Tenancy) -> dict[str, Tenancy]:
    """``sa.Table(..., info=...)`` に渡す宣言。"""
    return {TENANCY_KEY: kind}


def declared(kind: Tenancy) -> dict[str, dict[str, Tenancy]]:
    """``__table_args__`` に渡す宣言。"""
    return {"info": tenancy_info(kind)}


__all__ = ["TENANCY_KEY", "Tenancy", "declared", "tenancy_info"]
