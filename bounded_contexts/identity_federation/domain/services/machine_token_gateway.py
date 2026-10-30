"""機械のトークン（assay の ``client_credentials``）を確かめる口（ADR-0082 §1）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class MachineTokenGateway(Protocol):
    def verify_machine_token(self, issuer: str, audience: str, token: str) -> Mapping[str, Any]:
        """署名・発行者・期限・宛名（``aud``）を確かめてクレームを返す。

        合わなければ ``InvalidMachineTokenError``、IdP に届かなければ ``IdentityProviderUnavailableError``。
        ⚠ 宛名は必ず確かめる（空で呼ばない。呼ぶ側が先に断る）。
        """
        ...


__all__ = ["MachineTokenGateway"]
