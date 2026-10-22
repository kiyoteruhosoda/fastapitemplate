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

from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)


@dataclass(frozen=True)
class LoginTransaction:
    state: str
    nonce: str
    code_verifier: str
    redirect_to: str = "/"
    #: この往復が何のために始まったか（ADR-0040）。
    purpose: TransactionPurpose = TransactionPurpose.LOGIN
    #: 連携の往復を始めた利用者。ログインの往復では ``None``。
    #:
    #: ⚠ **戻ってきたときのセッションと突き合わせるためにある。** これが無いと、
    #:   往復の途中で別の利用者に入れ替わったブラウザが、**その人の口座へ**
    #:   結び付けてしまう。
    user_id: int | None = None
    #: 送り出した先の発行者（＝テナント。ADR-0061）。戻りはこの発行者のクライアントで受ける。
    #:
    #: ⚠ **戻りのときにクエリから決め直さない。** テナントを URL で選び直せると、あるテナントで
    #:   始めた往復を別のテナントの利用者として完了させられる。
    issuer: str = ""
    #: 画面を出さずに試した往復（``prompt=none``。ADR-0066）。
    #:
    #: ⚠ **戻りで「入っていない」と言われたときの扱いを決めるためにある。** 試しただけなので
    #:   失敗ではなく、エラーを出さずにログイン画面へ戻す。
    silent: bool = False

    def is_for(self, issuer: str) -> bool:
        """この往復が、その発行者へ送り出したものか。"""
        return bool(self.issuer) and compare_digest(self.issuer, issuer)

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

    def belongs_to(self, user_id: int) -> bool:
        """連携の往復を始めたのが、いま入っているこの利用者か。"""
        return self.user_id is not None and self.user_id == user_id


__all__ = ["LoginTransaction"]
