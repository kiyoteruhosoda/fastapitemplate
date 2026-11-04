"""アプリから来たトークンと、その出し方（ADR-0081 §1・ADR-0103）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresentedAppToken:
    """``Authorization`` の方式・``DPoP`` の証明・要求の宛先をまとめたもの。

    ``cnf.jkt`` のあるトークンは ``DPoP`` の方式と証明が要り、無いトークンは ``Bearer`` だけ。
    """

    token: str
    #: ``Authorization: DPoP`` で来たか（``False`` は ``Bearer``）。
    dpop: bool
    #: ``DPoP`` ヘッダーの証明。
    proof: str | None
    #: 大文字の HTTP メソッド。
    method: str
    #: このサーバーが外へ名乗る、この口の URL（問い合わせは付けない）。
    uri: str
    #: アプリが同じログインで受け取った ID トークン。結び付けたトークンで初めて来たときのプロフィールに使う。
    id_token: str | None = None


__all__ = ["PresentedAppToken"]
