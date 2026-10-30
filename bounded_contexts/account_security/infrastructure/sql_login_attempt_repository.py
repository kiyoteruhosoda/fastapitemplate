"""失敗の控えの SQLAlchemy 実装。

⚠ **リクエストのセッションを使わない。** 失敗の記録は 401 と一緒に返る ——つまり
例外で抜けるので、リクエストのセッションに書いても rollback で消える。監査ログが
リクエストの外で書くのと同じ事情（ADR-0075 §1）で、こちらは**操作ごとに短い
セッションを開いて commit する**。

SQLite の書き込みロックと衝突しないのは、呼ばれる時点でリクエストのセッションが
まだ何も書いていないため（照合の前・再設定の要求の前に呼ぶ）。順序を変えると
ここが詰まる。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session, sessionmaker

from bounded_contexts.account_security.domain.entities.login_attempts import (
    LoginAttempts,
    ThrottlePolicy,
)
from bounded_contexts.account_security.infrastructure.account_security_models import (
    LoginAttemptRecord,
)


@dataclass(frozen=True)
class SqlLoginAttemptRepository:
    session_factory: sessionmaker[Session]

    def get(self, purpose: str, identifier: str) -> LoginAttempts:
        with self.session_factory() as session:
            record = session.get(LoginAttemptRecord, (purpose, identifier))
            if record is None:
                return LoginAttempts(purpose=purpose, identifier=identifier)
            return LoginAttempts(
                purpose=record.purpose,
                identifier=record.identifier,
                failures=record.failures,
                window_started_at=record.window_started_at,
                locked_until=record.locked_until,
            )

    def save(self, attempts: LoginAttempts, now: datetime, policy: ThrottlePolicy) -> None:
        with self.session_factory() as session:
            # 未知の宛名の行がたまる（存在を漏らさないために数えている）ので、
            # 書くたびに「窓も断りも過ぎた行」を掃除する。専用のジョブは持たない
            _sweep(session, now, policy)
            record = session.get(LoginAttemptRecord, (attempts.purpose, attempts.identifier))
            if record is None:
                record = LoginAttemptRecord(purpose=attempts.purpose, identifier=attempts.identifier)
                session.add(record)
            record.failures = attempts.failures
            record.window_started_at = attempts.window_started_at
            record.locked_until = attempts.locked_until
            session.commit()

    def forget(self, purpose: str, identifier: str) -> None:
        with self.session_factory() as session:
            session.execute(
                delete(LoginAttemptRecord).where(
                    LoginAttemptRecord.purpose == purpose,
                    LoginAttemptRecord.identifier == identifier,
                )
            )
            session.commit()


def _sweep(session: Session, now: datetime, policy: ThrottlePolicy) -> None:
    stale_window = now - policy.window
    session.execute(
        delete(LoginAttemptRecord).where(
            or_(LoginAttemptRecord.locked_until.is_(None), LoginAttemptRecord.locked_until <= now),
            or_(
                LoginAttemptRecord.window_started_at.is_(None),
                LoginAttemptRecord.window_started_at <= stale_window,
            ),
        )
    )


__all__ = ["SqlLoginAttemptRepository"]
