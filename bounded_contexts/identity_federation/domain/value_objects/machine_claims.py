"""機械のトークンの主体（ADR-0082 §1 決定 3）。

署名・発行者・期限・宛名はゲートウェイが確かめる。ここで見るのは**主体がクライアント自身であること**:

- ``sub_type == "client"`` —— 利用者のログイン用トークンと見分ける唯一の印
- ``sub == client_id`` —— assay は 2 つを別々の材料から組み立てるので、揃っていることを確かめる

⚠ 実装ごとに覚えさせず、ここ 1 か所に持つ（忘れると、誰かのログイン用トークンで機械の口が通る）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bounded_contexts.identity_federation.domain.exceptions import InvalidMachineTokenError

CLIENT_SUBJECT_TYPE = "client"


@dataclass(frozen=True)
class MachineClaims:
    client_id: str

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> MachineClaims:
        if claims.get("sub_type") != CLIENT_SUBJECT_TYPE:
            raise InvalidMachineTokenError
        subject = claims.get("sub")
        client_id = claims.get("client_id")
        if not isinstance(subject, str) or not subject or subject != client_id:
            raise InvalidMachineTokenError
        return cls(client_id=subject)


__all__ = ["CLIENT_SUBJECT_TYPE", "MachineClaims"]
