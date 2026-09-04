"""ログインの往復で使う 1 回限りの値の生成と、その保存形。

``state`` / ``nonce`` / PKCE の ``code_verifier`` / 引き換え券はいずれも
「推測できないこと」だけが要件で、生成の仕方をばらけさせる理由が無い。
1 か所に集める。

引き換え券は持ち主へ渡す資格情報なので、DB へは SHA-256 のハッシュだけを置く
（漏れた控えからそのままログインできないようにする）。
"""

from __future__ import annotations

import base64
import hashlib
import secrets

# 128 bit 以上あれば総当たりは現実的でない。RFC 7636 は code_verifier に
# 43〜128 文字を求めており、32 バイトの base64url（43 文字）はその下限を満たす。
_TOKEN_BYTES = 32


def new_secret() -> str:
    """推測できない URL 安全な文字列を作る（state / nonce / 引き換え券）。"""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def new_code_verifier() -> str:
    """PKCE の ``code_verifier``（RFC 7636）。"""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def code_challenge_of(code_verifier: str) -> str:
    """``code_verifier`` から ``S256`` の ``code_challenge`` を作る。

    ``plain`` は使わない。認可要求を覗ける相手がそのまま検証値を得てしまい、
    PKCE の意味が無くなる。
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def hash_secret(value: str) -> str:
    """保存用のハッシュ。突き合わせは常にハッシュ同士で行う。"""
    return hashlib.sha256(value.encode()).hexdigest()


__all__ = ["code_challenge_of", "hash_secret", "new_code_verifier", "new_secret"]
