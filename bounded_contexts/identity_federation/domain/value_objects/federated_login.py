"""IdP 経由で始まった、このアプリのセッション 1 つ分（ADR-0036）。

宛名（:class:`FederatedSession`）に**いつ始まったか**を添えたもの。停止の記録は
「この時刻より前に始まったセッションを無効にする」という形で効くので、時刻が要る。

⚠ **トークンを発行した時刻ではなく、セッションが始まった時刻である。** 更新の
たびに新しくすると、**更新を 1 回通すだけで停止をすり抜けられる**（更新で出る
トークンの ``iat`` は必ず停止より後になるため）。

⚠ **トークンの ``iat`` では代用できない。** ``iat`` は秒までしか持たないので、
止めた直後の同じ秒にログインし直した利用者を巻き添えにする。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)


@dataclass(frozen=True)
class FederatedLogin:
    session: FederatedSession
    started_at: datetime


__all__ = ["FederatedLogin"]
