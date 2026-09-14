"""「このセッションはもう使わせない」という記録（ADR-0036）。

このテンプレートのセッションは**サーバーに控えの無い JWT** なので、届いた停止を
即座に反映する場所が無い。そこで「いつ止まったか」を行として残し、
**その時刻より前に発行されたトークンを無効**として扱う。

``expires_at`` は掃除のためだけにある。リフレッシュトークンの寿命を過ぎれば、
その時刻より前に発行されたトークンは自力で期限切れになるので、行を残す意味が無くなる。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)
from bounded_contexts.identity_federation.domain.value_objects.logout_notice import (
    LogoutNotice,
)


@dataclass(frozen=True)
class SessionRevocation:
    jti: str
    session: FederatedSession
    revoked_at: datetime
    expires_at: datetime

    @classmethod
    def of(cls, notice: LogoutNotice, *, now: datetime, keep_for_seconds: int) -> SessionRevocation:
        """通知を記録へ落とす。

        ``revoked_at`` は**受け取った時刻**で、``logout_token`` の ``iat`` ではない。
        再送された古い通知で、いま生きているセッションを巻き添えにしないため
        （再送そのものは ``jti`` で弾くが、時刻の出所は分けておく）。
        """
        return cls(
            jti=notice.jti,
            session=notice.session,
            revoked_at=now,
            expires_at=now + timedelta(seconds=keep_for_seconds),
        )

    def covers(self, login: FederatedLogin) -> bool:
        """このログインを、この記録が無効にするか。

        ``session_id`` が ``None`` の記録は**その利用者のすべてのセッション**に効く。
        比べるのは**セッションが始まった時刻**で、止めたあとに入り直した利用者は
        巻き添えにしない。
        """
        target = login.session
        if (self.session.issuer, self.session.subject) != (target.issuer, target.subject):
            return False
        if self.session.session_id is not None and self.session.session_id != target.session_id:
            return False
        return login.started_at <= self.revoked_at


__all__ = ["SessionRevocation"]
