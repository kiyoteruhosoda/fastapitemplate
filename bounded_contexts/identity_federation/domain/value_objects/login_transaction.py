"""認可要求の往復状態（``state`` / ``nonce`` / PKCE の ``code_verifier`` / 戻り先）。

IdP へリダイレクトで離れて戻ってくる**その間だけ**必要になる値をまとめたもの。
サーバー側に控えを持たず、**改竄できない形でブラウザに預ける**（ADR-0025）。
署名と Cookie の出し入れは Presentation 層（``presentation.transaction_cookie``）が
担い、ここは値と「戻りが同じ往復のものか」の判断だけを持つ。

⚠ **`code_verifier` を持つので、これは資格情報である。** Cookie は ``HttpOnly`` に
する（JavaScript から読めてはならない）。
"""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest


@dataclass(frozen=True)
class LoginTransaction:
    state: str
    nonce: str
    code_verifier: str
    redirect_to: str = "/"

    def matches(self, state: str) -> bool:
        """戻ってきた ``state`` が、この往復で送り出したものか。

        **Cookie が無ければこの判断自体が成立しない**（呼び出し側で往復状態を
        復元できない）。表に控えを置く形と違い、``state`` を知っているだけの
        相手は戻りを完了できない ——攻撃者が始めた認可要求を踏まされても、
        被害者のブラウザには対応する Cookie が無いため（ログイン CSRF）。

        照合は :func:`hmac.compare_digest` で行う（応答時間から一致した文字数を
        推測されないようにする）。
        """
        return bool(state) and compare_digest(self.state, state)


__all__ = ["LoginTransaction"]
