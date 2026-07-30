"""WebAuthn チャレンジの永続化インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    WebAuthnChallenge,
)


class WebAuthnChallengeRepository(Protocol):
    def issue(self, challenge: WebAuthnChallenge) -> WebAuthnChallenge:
        """チャレンジを保存する。期限切れのものはこの機会に掃除する。"""

    def consume(self, challenge_id: str, purpose: str) -> WebAuthnChallenge:
        """チャレンジを取り出して破棄する（1 回限り）。

        見つからない・用途が違う・期限切れの場合は
        :class:`~bounded_contexts.account_security.domain.exceptions.ChallengeNotFoundError`。
        """


__all__ = ["WebAuthnChallengeRepository"]
