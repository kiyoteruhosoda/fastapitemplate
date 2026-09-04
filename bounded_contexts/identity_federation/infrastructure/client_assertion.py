"""``private_key_jwt`` のクライアント認証アサーション（RFC 7523 / OIDC Core §9）。

秘密鍵はホスト上のファイルにあり、**署名のときだけ読む**。アプリの設定に載るのは
在り処と ``kid`` だけで、鍵そのものはデプロイの変数にも DB にも現れない
（ADR-0025）。

自前 idp 側の検証（実装を読んで確認したもの）:

- ``client_assertion_type`` は ``urn:ietf:params:oauth:client-assertion-type:jwt-bearer`` のみ
- ``iss`` と ``sub`` はどちらも **client_id 自身**（RFC 7523 §3）
- ``aud`` は ``<issuer>/token`` か ``<issuer>`` のどちらか
- **``jti`` 必須**。再生防止のため IdP 側が記録する
- ``exp`` は **今から 5 分以内**。超えると ``assertion_lifetime_too_long``
- 検証アルゴリズムは**登録済み鍵の種別**から決まる。ヘッダの ``alg`` は信用されない
  （alg 混同攻撃を成立させないため）
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import jwt

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.value_objects.client_credential import (
    ClientCredential,
)
from shared.kernel.timestamps import utcnow

logger = logging.getLogger(__name__)

ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# ⚠ idp の上限は 5 分。短くしておく理由は、長くしても得るものが無く、再生の窓と
#   IdP 側が jti を保持する期間を伸ばすだけだから。
_LIFETIME_SECONDS = 60

_ALGORITHM = "RS256"


@dataclass(frozen=True)
class ClientAssertionRequest:
    """アサーションを 1 通作るための入力。

    ``client_id`` と ``audience`` はどちらも ``str`` で、位置引数で渡すと取り違えが
    型検査を抜ける。取り違えれば IdP 側で ``invalid_client`` になるが、**どれで
    落ちたかは返ってこない**ので、入口でまとめて運ぶ。
    """

    client_id: str
    audience: str
    credential: ClientCredential


def build_client_assertion(request: ClientAssertionRequest) -> str:
    """トークンエンドポイントへ提示する署名付きアサーションを組み立てる。"""
    now = utcnow()
    headers = {"typ": "JWT"}
    kid = request.credential.private_key_kid
    if kid:
        # 鍵が複数登録されていると、kid が無い限り IdP はどれで検証するか決められない。
        headers["kid"] = kid
    return jwt.encode(
        {
            "iss": request.client_id,
            "sub": request.client_id,
            "aud": request.audience,
            # 毎回異なる値。IdP が記録して再生を防ぐ。
            "jti": secrets.token_urlsafe(32),
            "iat": now,
            "exp": now + timedelta(seconds=_LIFETIME_SECONDS),
        },
        read_private_key(request.credential),
        algorithm=_ALGORITHM,
        headers=headers,
    )


def read_private_key(credential: ClientCredential) -> str:
    """署名鍵（PEM）を読む。読めなければ :class:`SsoNotConfiguredError`。

    ⚠ **読めるかどうかは使うときになって初めて分かる。** 権限が合っていなくても
    起動も設定の確認も通り、利用者が IdP から戻ってきた瞬間だけ落ちる。
    起動時にも一度確かめてログへ出す（``presentation/fastapi/app.py``）。
    """
    path = credential.private_key_file
    if not path:
        raise SsoNotConfiguredError
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        # 0400 root だとコンテナの実行ユーザーは読めない。ディレクトリ自身にも
        # 通り抜けの権限が要る（`/srv/secrets/oidc` は 0710 root:5678）。
        logger.error("sso_private_key_unreadable", extra={"reason": type(error).__name__})
        raise SsoNotConfiguredError from error


__all__ = ["ASSERTION_TYPE", "ClientAssertionRequest", "build_client_assertion", "read_private_key"]
