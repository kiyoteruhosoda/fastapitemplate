"""DPoP（RFC 9449）の証明に求めることと、確かめ終えた証明（ADR-0103）。

assay と同じ幅で受ける（assay の ADR-0075 決定 6）: ``iat`` は今より 120 秒前から 60 秒後まで。
``jti`` は鍵ごとに 1 回だけで、受ける幅が閉じるまで覚える。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

#: ``iat`` が今よりどれだけ前まで受けるか。
MAX_PROOF_AGE = timedelta(seconds=120)
#: ``iat`` が今よりどれだけ先まで受けるか（端末の時計が進んでいる分）。
MAX_CLOCK_AHEAD = timedelta(seconds=60)


@dataclass(frozen=True)
class DpopProofRequirements:
    """証明が満たすべきこと。

    ``uri`` は**このサーバーが外へ名乗る URL**（``APP_BASE_URL`` ＋パス）。前段の proxy の後ろで
    ``Host`` から組み立てると、アプリが署名した URL と食い違う。
    """

    method: str
    uri: str
    access_token: str
    #: tz 付きの UTC。
    now: datetime


@dataclass(frozen=True)
class VerifiedDpopProof:
    #: 鍵の指紋（RFC 7638 の JWK Thumbprint）。トークンの ``cnf.jkt`` と比べる。
    jkt: str
    jti: str
    #: tz 付きの UTC。
    issued_at: datetime

    @property
    def replay_key(self) -> str:
        """使い回しを見る記録の鍵。``jti`` の一意性は鍵ごと。"""
        return hashlib.sha256(f"{self.jkt}:{self.jti}".encode()).hexdigest()

    @property
    def retain_until(self) -> datetime:
        """この時刻を過ぎれば、同じ証明は時刻で断られる（記録はここまで残せば足りる）。"""
        return self.issued_at + MAX_PROOF_AGE


__all__ = ["MAX_CLOCK_AHEAD", "MAX_PROOF_AGE", "DpopProofRequirements", "VerifiedDpopProof"]
