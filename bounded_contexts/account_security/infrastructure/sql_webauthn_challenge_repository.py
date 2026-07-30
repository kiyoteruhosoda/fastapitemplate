"""WebAuthn チャレンジの SQLAlchemy 実装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    WebAuthnChallenge,
)
from bounded_contexts.account_security.domain.exceptions import ChallengeNotFoundError
from bounded_contexts.account_security.infrastructure.account_security_models import (
    WebAuthnChallengeRecord,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class SqlWebAuthnChallengeRepository:
    session: Session

    def issue(self, challenge: WebAuthnChallenge) -> WebAuthnChallenge:
        # 期限切れは放っておくと溜まり続けるため、発行のたびに掃除する。
        # 専用の定期ジョブを持たない構成でもテーブルが肥大しない。
        self.session.execute(delete(WebAuthnChallengeRecord).where(WebAuthnChallengeRecord.expires_at < utcnow()))
        self.session.add(
            WebAuthnChallengeRecord(
                challenge_id=challenge.challenge_id,
                challenge=challenge.challenge,
                purpose=challenge.purpose,
                user_id=challenge.user_id,
                expires_at=challenge.expires_at,
            )
        )
        self.session.flush()
        return challenge

    def consume(self, challenge_id: str, purpose: str) -> WebAuthnChallenge:
        record = self.session.get(WebAuthnChallengeRecord, challenge_id)
        if record is None or record.purpose != purpose:
            raise ChallengeNotFoundError

        challenge = WebAuthnChallenge(
            challenge_id=record.challenge_id,
            challenge=record.challenge,
            purpose=record.purpose,
            user_id=record.user_id,
            expires_at=record.expires_at,
        )

        # 「読んでから消す」だと、同じ assertion を同時に 2 回送られたとき、
        # どちらの削除も確定する前に両方が読み終えてしまい、2 本ともトークンを
        # 得られる。消費は **削除の成否**（1 行消せたか）で決める。DELETE は
        # 行ロックを取るため、後続は先行のコミットを待ってから 0 行を返す。
        result = cast(
            "CursorResult[Any]",
            self.session.execute(
                delete(WebAuthnChallengeRecord).where(WebAuthnChallengeRecord.challenge_id == challenge_id),
                # 同期方法を方言任せにせず、消えた行の後始末は expunge で明示する
                execution_options={"synchronize_session": False},
            ),
        )
        deleted = result.rowcount
        self.session.expunge(record)
        if deleted != 1:
            raise ChallengeNotFoundError

        # 期限切れでも削除は済ませる（再送で粘られないように）
        if challenge.is_expired(utcnow()):
            raise ChallengeNotFoundError
        return challenge


__all__ = ["SqlWebAuthnChallengeRepository"]
