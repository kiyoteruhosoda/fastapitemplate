"""A record saying "this session may no longer be used" (ADR-0077 §3).

This template's sessions are **JWTs with no server-side copy**, so there's no place to apply
an incoming logout immediately. Instead, "when it was stopped" is kept as a row, and
**tokens issued before that time are treated as invalid**.

``expires_at`` exists only for cleanup. Past the refresh token lifetime, tokens issued
before that time expire on their own, so keeping the row no longer serves any purpose.
This sets the minimum length; if current logins last longer, it is extended on save (ADR-0102).
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
        """Turn a notice into a record.

        ``revoked_at`` is **the time it was received**, not the ``logout_token``'s ``iat``.
        This keeps a resent old notice from taking down sessions alive now
        (resends themselves are rejected by ``jti``, but the time source is kept separate).
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
        """Stop **all** SSO sessions of a person assay reported as "no longer usable" in the periodic
        reconciliation (ADR-0077 §7).

        ⚠ **``jti`` is derived from ``(issuer, sub, time of last SSO sign-in)``.**

        - For the same login, **one row** suffices even if it runs hourly on every worker
          (the second is rejected by :meth:`SessionRevocationRepository.record` as a duplicate ``jti``)
        - If restored in assay, signed in again, and stopped again, the time differs, so it is **a new row**.
          ⚠ With the same ``jti`` the old row would remain, the new one wouldn't be written, and the
          re-signed-in session would be missed (a record only affects sessions started before its time)

        The ``jti`` column is 64 characters, so the inputs are hashed to fit. A prefix is mixed into
        the inputs to keep a separate space from ``jti`` values issued by the IdP.
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
        """Whether this record invalidates this login.

        A record with ``session_id`` ``None`` applies to **all sessions of that user**.
        What's compared is **the time the session started**, so users who signed in again after
        the stop are not caught up in it.
        """
        target = login.session
        if (self.session.issuer, self.session.subject) != (target.issuer, target.subject):
            return False
        if self.session.session_id is not None and self.session.session_id != target.session_id:
            return False
        return login.started_at <= self.revoked_at


__all__ = ["SessionRevocation"]
