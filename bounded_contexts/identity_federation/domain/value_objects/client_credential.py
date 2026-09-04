"""トークンエンドポイントへ名乗るときの資格情報（ADR-0025）。

方式は 2 つある。どちらも「クライアント本人であること」を示す手段で、
**認可コードの引き換えのときだけ**使う。

``client_secret_basic``
    共有された秘密を Basic 認証で送る。設定に秘密そのものを持つ。
``private_key_jwt``
    ホスト上の秘密鍵で署名したアサーションを送る（RFC 7523）。設定に載るのは
    **鍵の在り処**だけで、秘密そのものはアプリの設定にもデプロイの変数にも
    現れない。
"""

from __future__ import annotations

from dataclasses import dataclass

CLIENT_SECRET_BASIC = "client_secret_basic"
PRIVATE_KEY_JWT = "private_key_jwt"

#: 設定として受け付ける方式。ここに無い値は「不備」として扱う（ADR-0025）。
CLIENT_AUTH_METHODS = (CLIENT_SECRET_BASIC, PRIVATE_KEY_JWT)


@dataclass(frozen=True)
class ClientCredential:
    """方式と、その方式が要る材料。

    材料は方式ごとに違うので、**揃っているかの判断も方式ごとに変わる**。
    ここで持たない値（空文字）は「設定されていない」を意味する。
    """

    method: str
    secret: str = ""
    private_key_file: str = ""
    private_key_kid: str = ""

    @property
    def is_complete(self) -> bool:
        """その方式で名乗れるだけの材料が揃っているか。

        ⚠ **綴り違いを既定の方式へ落とさない。** ``private-key-jwt`` のような値を
        黙って ``client_secret_basic`` として扱うと、IdP からは理由の分からない
        ``invalid_client`` が返るだけになる。知らない方式は不備とする。
        """
        if self.method == PRIVATE_KEY_JWT:
            return bool(self.private_key_file)
        if self.method == CLIENT_SECRET_BASIC:
            return bool(self.secret)
        return False

    @property
    def uses_private_key(self) -> bool:
        return self.method == PRIVATE_KEY_JWT


__all__ = [
    "CLIENT_AUTH_METHODS",
    "CLIENT_SECRET_BASIC",
    "PRIVATE_KEY_JWT",
    "ClientCredential",
]
