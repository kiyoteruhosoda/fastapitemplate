"""SQLAlchemy implementation of the gateway to users (``users``).

This is the only place that touches the ``shared`` ``User`` / ``Role`` models; the identity
federation Domain / Application layers don't know this implementation.

It only handles **users of the issuer's tenant** (ADR-0079 §1). The issuer represents the
tenant, so it neither merges people of another tenant by email nor creates them in another tenant.
If ``tenant_id`` is ``None`` (unregistered issuer), nobody can be found or created.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace

import sqlalchemy as sa
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from bounded_contexts.account_security.infrastructure.account_security_models import PasskeyCredentialRecord
from bounded_contexts.identity_federation.domain.entities.federated_account import (
    FederatedAccount,
    NewFederatedAccount,
)
from bounded_contexts.identity_federation.domain.exceptions import SsoAccountNotLinkedError
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import FederatedIdentityRecord
from shared.infrastructure.models import Role, User
from shared.infrastructure.tenant_scope import TenantMembers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SqlFederatedUserDirectory:
    session: Session
    tenant_id: int | None

    def _users(self) -> Select[User]:
        if self.tenant_id is None:
            return select(User).where(sa.false())
        return TenantMembers(self.session, self.tenant_id).users_query()

    def find_by_id(self, user_id: int) -> FederatedAccount | None:
        return _as_account(self.session.scalar(self._users().where(User.id == user_id)))

    def find_by_email(self, email: str) -> FederatedAccount | None:
        """Look up by email. **The exact-spelling row first; if none, case-insensitively.**

        ⚠ **Don't look up with ``==`` alone.** PostgreSQL is case-sensitive, so a user created as
        ``Claude@nolumia.com`` isn't reached via ``claude@nolumia.com``. Neither the email returned by
        idp nor the machine's ``acts_as`` is guaranteed to match the spelling of our rows.

        ⚠ **Case-insensitive lookup may not resolve to one row.** The unique constraint on
        ``users.email`` is case-sensitive, so ``Alice@…`` and ``alice@…`` can both exist (the admin
        screen saves as typed). Silently returning "the first row" would make the user a machine acts
        as, or the one bound via SSO, depend on the query plan. **If it can't be resolved, refuse as
        "not found"** (logged, without the value).
        """
        exact = self.session.scalar(self._users().where(User.email == email))
        if exact is None:
            normalized = email.strip().lower()
            matches = self.session.scalars(self._users().where(func.lower(User.email) == normalized)).all()
            if len(matches) > 1:
                logger.warning("federated_email_ambiguous", extra={"matches": len(matches)})
                return None
            exact = matches[0] if matches else None
        if exact is None:
            return None
        return replace(_require_account(exact), awaiting_owner=self._awaiting_owner(exact))

    def _awaiting_owner(self, user: User) -> bool:
        """Whether this is a seat that is invited but has no way in at all (ADR-0079 §5)."""
        if user.has_local_password:
            return False
        linked = select(FederatedIdentityRecord.user_id).where(FederatedIdentityRecord.user_id == user.id)
        passkeys = select(PasskeyCredentialRecord.user_id).where(PasskeyCredentialRecord.user_id == user.id)
        return self.session.scalar(linked.union_all(passkeys).limit(1)) is None

    def provision(self, account: NewFederatedAccount) -> FederatedAccount:
        if self.tenant_id is None:
            # Unregistered issuer. There is no tenant to create in
            raise SsoAccountNotLinkedError
        user = User(
            email=account.email,
            username=account.username,
            # ⚠ **Don't fill with a random value** (ADR-0076 §6). That would make "no password" and
            # "a password nobody knows" indistinguishable, distorting things: the screen would offer a
            # change path, and audit couldn't tell which ways in exist.
            password_hash=None,
            is_active=True,
        )
        user.roles = self._roles_named(account.roles)
        user.join(self.tenant_id)
        self.session.add(user)
        self.session.flush()
        logger.info("sso_user_provisioned")
        return _require_account(user)

    def refresh_profile(self, user_id: int, *, email: str | None, username: str) -> None:
        """Overwrite name and email in the copy (ADR-0077 §6).

        ⚠ **Don't write conflicting values.** ``users.email`` and ``users.username`` are both unique,
        so writing a value another user already has **makes the login fail with a 500**.
        Breaking login for a copy update defeats the purpose, so only that field is skipped and recorded.
        """
        user = self.session.get(User, user_id)
        if user is None:  # pragma: no cover - only if the user just looked up has vanished
            return
        if email is not None and email != user.email and self._is_free(User.email, email, user_id):
            user.email = email
        if username and username != user.username and self._is_free(User.username, username, user_id):
            user.username = username
        self.session.flush()

    def _is_free(self, column: InstrumentedAttribute[str], value: str, user_id: int) -> bool:
        taken = self.session.scalar(self._users().with_only_columns(User.id).where(column == value, User.id != user_id))
        if taken is not None:
            # ⚠ Don't record the values themselves (PII). Knowing which fields were skipped is enough.
            logger.warning("federated_profile_conflict", extra={"field": column.key})
            return False
        return True

    def apply_roles(self, user_id: int, roles: Sequence[str]) -> FederatedAccount:
        user = self.session.get(User, user_id)
        if user is None:
            raise LookupError(user_id)
        resolved = self._roles_named(roles)
        if not resolved:
            # When nothing matches, leave it alone. Avoids everyone losing permissions (nobody able
            # to enter the admin screen) just from a mistyped group claim name.
            logger.warning("sso_role_sync_skipped_no_match")
            return _require_account(user)
        user.roles = resolved
        self.session.flush()
        return _require_account(user)

    def _roles_named(self, names: Sequence[str]) -> list[Role]:
        """Look up roles by name. Unknown names and roles not usable in the tenant are silently dropped."""
        if not names or self.tenant_id is None:
            return []
        return list(TenantMembers(self.session, self.tenant_id).roles_named(names))


def _as_account(user: User | None) -> FederatedAccount | None:
    return None if user is None else _require_account(user)


def _require_account(user: User) -> FederatedAccount:
    return FederatedAccount(
        user_id=user.id,
        email=user.email,
        is_active=user.is_active,
        roles=user.role_names,
    )


__all__ = ["SqlFederatedUserDirectory"]
