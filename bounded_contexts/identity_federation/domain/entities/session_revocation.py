"""「このセッションはもう使わせない」という記録（ADR-0036）。

このテンプレートのセッションは**サーバーに控えの無い JWT** なので、届いた停止を
即座に反映する場所が無い。そこで「いつ止まったか」を行として残し、
**その時刻より前に発行されたトークンを無効**として扱う。

``expires_at`` は掃除のためだけにある。リフレッシュトークンの寿命を過ぎれば、
その時刻より前に発行されたトークンは自力で期限切れになるので、行を残す意味が無くなる。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
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

    @classmethod
    def after_reconciliation(
        cls,
        identity: FederatedIdentity,
        *,
        now: datetime,
        keep_for_seconds: int,
    ) -> SessionRevocation:
        """定期照合で assay が「もう使えない」と答えた人の、**すべての** SSO セッションを止める（ADR-0043）。

        ⚠ **``jti`` を ``(issuer, sub, 最後に SSO で入った時刻)`` から決める。**

        - 同じログインに対しては、毎時・ワーカーの数だけ走っても**行は 1 本**で済む
          （2 本目は ``jti`` の重複として :meth:`SessionRevocationRepository.record` が弾く）
        - assay で戻って入り直し、また止められたときは時刻が変わるので**新しい行**になる。
          ⚠ 同じ ``jti`` のままだと古い行が残って新しい行が書かれず、入り直した
          セッションを取りこぼす（記録は「その時刻より前に始まったもの」にしか効かない）

        ``jti`` の列は 64 文字なので、材料はハッシュにして収める。IdP が発行する ``jti`` とは
        材料に前置きを混ぜて空間を分けてある。
        """
        generation = identity.last_login_at or identity.linked_at
        material = "|".join(
            ("sso-reconciliation", identity.issuer, identity.subject, generation.isoformat() if generation else "")
        )
        return cls(
            jti=hashlib.sha256(material.encode("utf-8")).hexdigest(),
            session=FederatedSession(issuer=identity.issuer, subject=identity.subject, session_id=None),
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
