"""JWT issuance and verification (two tokens, access / refresh; SSO logins get access only;
ADR-0104).

- The scope claim is within the user's held permissions. Missing or empty = no permissions.
- The ``active_role`` claim is "which role is being used now" (ADR-0078 §1).
  ``None`` means "all roles" = union of held permissions. If set, scope is narrowed to that one
  role's permissions. Switching is done by issuing a new token.
- ``fed_iss`` / ``fed_sub`` / ``sid`` / ``fed_iat`` are the identifiers and **start time** of a
  session started via the IdP (ADR-0077 §3). **Checked against suspensions on every
  verification**: the server keeps no session record, so a received termination can only take
  effect here. Not present on tokens issued for local logins.
- The verification result is returned as an ``AuthenticatedPrincipal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.application.dto.sso_dto import ContinuedSessionDto
from bounded_contexts.identity_federation.application.use_cases.check_session_revocation import (
    CheckSessionRevocation,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from presentation.fastapi.services import refresh_sessions
from presentation.fastapi.services.refresh_sessions import RefreshStanding
from presentation.fastapi.services.session_carry_over import FRESH_SIGN_IN, SessionCarryOver
from presentation.fastapi.services.two_factor_requirement import needs_two_factor_setup
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import RefreshSession, User
from shared.infrastructure.tenant_scope import tenant_admits
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow_aware

_ALGORITHM = "HS256"
TYPE_ACCESS = "access"
TYPE_REFRESH = "refresh"
TYPE_LOGOUT = "logout"
# Claim name carrying the active role name (put in both access and refresh;
# without it in refresh, every token refresh would revert to "all roles")
CLAIM_ACTIVE_ROLE = "active_role"
# Identifiers of the IdP-side session (ADR-0077 §3). Only ``sid`` uses the OIDC spelling
# (to make it readable as a value copied from the ID token).
CLAIM_FEDERATED_ISSUER = "fed_iss"
CLAIM_FEDERATED_SUBJECT = "fed_sub"
CLAIM_SESSION_ID = "sid"
# Session start time (microseconds since the epoch). ``iat`` only has seconds and would catch
# a user who signed in again within the same second right after a termination, so it is separate.
CLAIM_FEDERATED_ISSUED_AT = "fed_iat"
# Time the user last actually signed in (epoch seconds; OIDC spelling; ADR-0076 §10).
# Carried over on refresh and role switch, never renewed.
CLAIM_AUTHENTICATED_AT = "auth_time"
# Tenant the user belongs to (ADR-0079 §1). null for users outside any tenant.
# ⚠ **Tokens without the claim (pre-tenant ones) are rejected.** Reading it as null would leave
# the user "unable to see any tenant's data" until expiry, so 401 forces a refresh
# (the refresh reads the DB and reissues with the current membership).
CLAIM_TENANT = "tenant"
#: Marks a token issued by the machine endpoint (the claimed machine's ``client_id``; ADR-0087).
#: Not present on human tokens.
#: ⚠ Tokens carrying it pass only scope-guarded endpoints (``require_permission``).
CLAIM_MACHINE_CLIENT = "machine_client"
#: The login record (``refresh_sessions.id``; ADR-0091). Also put in access tokens and carried
#: over on role switch
CLAIM_REFRESH_SESSION = "rsid"
# Mark for passkey logins (access / refresh; not dropped on refresh) and mark for pending
# two-factor enrollment (access only; re-decided on every refresh). ADR-0093
CLAIM_SIGNED_IN_WITH_PASSKEY = "passkey"
CLAIM_TWO_FACTOR_SETUP = "two_factor_setup"
#: How long the access token cookie of an SSO login is kept (ADR-0104). The token itself expires
#: in 5 minutes. The cookie outlives it so the silent continuation round trip can carry over the
#: role and sign-in time (:func:`continuation_of`). Matches the longest IdP login state (30 days)
RENEWAL_CARRY_SECONDS = 30 * 24 * 3600
#: Treatment of tokens without ``auth_time`` (from before this mechanism): "long ago"
SIGNED_IN_LONG_AGO = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class MachineAccessToken:
    """A token issued by the machine endpoint (ADR-0087)."""

    token: str
    expires_in: int
    #: Scopes actually included (overlap of allowlisted operations and the user's permissions)
    scopes: list[str]


@dataclass(frozen=True)
class RefreshedSession:
    """The refresh target. **The entrance (``federated_session``) is returned too** (ADR-0077 §3).

    Dropping it would lose the IdP session identifiers on every refresh, and **a single token
    refresh would slip past termination propagation**.
    """

    user: User
    active_role: str | None
    federated_login: FederatedLogin | None
    #: Time the user last actually signed in (ADR-0076 §10). Carried over on refresh too
    authenticated_at: datetime = SIGNED_IN_LONG_AGO
    signed_in_with_passkey: bool = False
    refresh_session_id: str = ""
    #: Identifier of the presented token and the result of comparing it with the record (ADR-0091)
    jti: str = ""
    standing: RefreshStanding = RefreshStanding.CURRENT

    @property
    def carry(self) -> SessionCarryOver:
        """What carries over to the new token (role, entrance, sign-in time)."""
        return SessionCarryOver(
            active_role=self.active_role,
            federated_login=self.federated_login,
            authenticated_at=self.authenticated_at,
            refresh_session_id=self.refresh_session_id,
            presented_jti=self.jti,
            signed_in_with_passkey=self.signed_in_with_passkey,
        )


class TokenService:
    @staticmethod
    def create_access_token(user: User, *, carry: SessionCarryOver) -> str:
        """Issue only an access token (SSO login; ADR-0104).

        Neither a refresh token nor a record (``rsid``) is created. On expiry the UI silently asks
        the IdP and signs in again if the IdP login state is still alive.
        """
        return _access_token(user, carry, _base_claims(user, carry, None, utcnow_aware()))

    @staticmethod
    def create_token_pair(
        user: User,
        *,
        scopes: list[str] | None = None,
        carry: SessionCarryOver = FRESH_SIGN_IN,
        refresh_expires_at: datetime | None = None,
    ) -> dict[str, object]:
        """Issue access / refresh tokens (password or passkey login).

        Even when ``scopes`` is given, it is trimmed to the intersection with the active role's
        permissions. Logins pending two-factor enrollment get no permissions (ADR-0093).
        ``refresh_expires_at`` is the expiry time matched with the record (naive UTC; ADR-0101).
        """
        now = utcnow_aware()
        refresh_session_id = carry.refresh_session_id or refresh_sessions.new_identifier()
        refresh_jti = refresh_sessions.new_identifier()
        expires_at = (
            refresh_expires_at.replace(tzinfo=UTC)
            if refresh_expires_at is not None
            else now + timedelta(seconds=settings.refresh_token_expires_seconds)
        )
        base_claims = _base_claims(user, carry, refresh_session_id, now)
        refresh = jwt.encode(
            {
                **base_claims,
                "type": TYPE_REFRESH,
                "jti": refresh_jti,
                "exp": expires_at,
            },
            settings.jwt_secret_key,
            algorithm=_ALGORITHM,
        )
        return {
            "access_token": _access_token(user, carry, base_claims, scopes),
            "refresh_token": refresh,
            "logout_token": _logout_token(user, refresh_session_id, now, expires_at),
            "refresh_session_id": refresh_session_id,
            "refresh_jti": refresh_jti,
            "token_type": "bearer",
            "expires_in": settings.access_token_expires_seconds,
        }

    @classmethod
    def verify_access_token_with_reason(cls, token: str) -> tuple[AuthenticatedPrincipal | None, str | None]:
        """Verify an access token **by signature and claims only** (ADR-0076 §5).

        ⚠ **Does not hit the DB.** Suspended users, removed permissions and IdP terminations are
        not visible here. **They are noticed at the next refresh**, so the access token lifetime
        (default 5 minutes) is the upper bound until then.

        ⚠ **This looseness is acceptable only because the refresh side is strict.**
        :meth:`verify_refresh_token` hits the DB and issues no new access token if suspended.
        **The suspension decision is concentrated in that one place.**
        """
        claims, reason = _decode(token)
        if claims is None:
            return None, reason
        if claims.get("type") != TYPE_ACCESS:
            return None, "not_access_token"
        if CLAIM_TENANT not in claims:
            return None, "token_outdated"
        try:
            user_id = int(claims.get("sub", ""))
        except ValueError:
            return None, "token_invalid"
        return (
            AuthenticatedPrincipal(
                user_id=user_id,
                email=str(claims.get("email") or ""),
                username=str(claims.get("username") or ""),
                permissions=frozenset(claims.get("scope") or ()),
                active_role=_active_role_of(claims),
                authenticated_at=_authenticated_at_of(claims),
                tenant_id=_tenant_of(claims),
                machine_client_id=_machine_client_of(claims),
                two_factor_setup_required=claims.get(CLAIM_TWO_FACTOR_SETUP) is True,
            ),
            None,
        )

    @classmethod
    def verify_refresh_token(cls, token: str, *, session: Session) -> RefreshedSession | None:
        """Return the user to refresh, plus the session's active role and entrance.

        ⚠ **The suspension decision is concentrated here** (ADR-0076 §5). Access token
        verification doesn't hit the DB, so **this is the only place a suspended user can be
        stopped**; loosening it removes the lifetime bound altogether.
        """
        claims, _ = _decode(token)
        if claims is None or claims.get("type") != TYPE_REFRESH:
            return None
        user = _load_active_user(claims, session)
        if user is None:
            return None
        if _session_revoked(claims, session):
            return None
        # ⚠ Tokens without a record (pre-ADR-0091) are rejected: reuse could not be detected
        refresh_session_id, jti = claims.get(CLAIM_REFRESH_SESSION), claims.get("jti")
        if not isinstance(refresh_session_id, str) or not isinstance(jti, str):
            return None
        row = session.get(RefreshSession, refresh_session_id)
        if row is None:
            return None
        return RefreshedSession(
            user=user,
            active_role=_active_role_of(claims),
            federated_login=_federated_login_of(claims),
            authenticated_at=_authenticated_at_of(claims),
            signed_in_with_passkey=claims.get(CLAIM_SIGNED_IN_WITH_PASSKEY) is True,
            refresh_session_id=refresh_session_id,
            jti=jti,
            standing=refresh_sessions.standing_of(row, jti),
        )

    @classmethod
    def end_refresh_session(cls, logout_token: str, *, session: Session) -> None:
        """Delete the login record identified by the logout token (ADR-0091). Unreadable tokens do
        nothing."""
        claims, _ = _decode(logout_token)
        if claims is None or claims.get("type") != TYPE_LOGOUT:
            return
        refresh_session_id = claims.get(CLAIM_REFRESH_SESSION)
        if isinstance(refresh_session_id, str):
            refresh_sessions.end(session, refresh_session_id)

    @classmethod
    def refresh_session_id_of(cls, token: str) -> str | None:
        """The login record carried in the access token (carried over on role switch)."""
        claims, _ = _decode(token)
        value = claims.get(CLAIM_REFRESH_SESSION) if claims is not None else None
        return value if isinstance(value, str) else None

    @classmethod
    def signed_in_with_passkey_of(cls, token: str) -> bool:
        """Whether the token is from a passkey login (ADR-0093). Carried over on reissue."""
        claims, _ = _decode(token)
        return claims is not None and claims.get(CLAIM_SIGNED_IN_WITH_PASSKEY) is True

    @classmethod
    def session_is_revoked(cls, token: str, *, session: Session) -> bool:
        """Whether this access token's session has been terminated at the IdP (ADR-0076 §5).

        ⚠ **Not called in ordinary verification.** Only paths that "issue new tokens" call it,
        checking the DB there alone; otherwise a suspended user could break the lifetime bound
        just by reissuing repeatedly.
        """
        claims, _ = _decode(token)
        if claims is None or claims.get("type") != TYPE_ACCESS:
            return False
        return _session_revoked(claims, session)

    @classmethod
    def federated_login_of(cls, token: str) -> FederatedLogin | None:
        """Read the IdP-side session from a verified access token.

        Used to carry it over when issuing a new token on role switch
        (without it, the switch would escape termination propagation).
        """
        claims, _ = _decode(token)
        if claims is None or claims.get("type") != TYPE_ACCESS:
            return None
        return _federated_login_of(claims)


def _decode(token: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            audience=settings.access_token_audience,
            issuer=settings.access_token_issuer,
        )
        return claims, None
    except jwt.ExpiredSignatureError:
        return None, "token_expired"
    except jwt.InvalidTokenError:
        return None, "token_invalid"


def _load_active_user(claims: dict[str, Any], session: Session) -> User | None:
    try:
        user_id = int(claims.get("sub", ""))
    except ValueError:
        return None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    # No reissue for members of a suspended tenant (ADR-0079 §1). A token in hand lasts until it
    # expires
    if not tenant_admits(session, user):
        return None
    return user


def continuation_of(token: str) -> ContinuedSessionDto | None:
    """Read what the continuation round trip carries over from an expired SSO access token
    (ADR-0104).

    ⚠ **This is not authentication.** The values are used only when **the same person** comes
    back from the IdP (to carry over the role and sign-in time). Signature, issuer and audience
    are checked; expiry is tolerated up to :data:`RENEWAL_CARRY_SECONDS`. Tokens not from an SSO
    login are not read.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            audience=settings.access_token_audience,
            issuer=settings.access_token_issuer,
            leeway=timedelta(seconds=RENEWAL_CARRY_SECONDS),
        )
    except jwt.InvalidTokenError:
        return None
    if claims.get("type") != TYPE_ACCESS or _federated_login_of(claims) is None:
        return None
    try:
        user_id = int(claims.get("sub", ""))
    except ValueError:
        return None
    return ContinuedSessionDto(
        user_id=user_id,
        active_role=_active_role_of(claims),
        authenticated_at=_authenticated_at_of(claims),
        signed_in_with_passkey=claims.get(CLAIM_SIGNED_IN_WITH_PASSKEY) is True,
    )


def _base_claims(
    user: User,
    carry: SessionCarryOver,
    refresh_session_id: str | None,
    now: datetime,
) -> dict[str, object]:
    """Claims common to access / refresh. If ``refresh_session_id`` is ``None``, no record is
    included (ADR-0104)."""
    claims: dict[str, object] = {
        "sub": str(user.id),
        "iss": settings.access_token_issuer,
        "aud": settings.access_token_audience,
        "iat": now,
        # ``None`` means "signed in just now" (password, passkey, SSO entrances)
        CLAIM_AUTHENTICATED_AT: int((carry.authenticated_at or now).timestamp()),
        CLAIM_ACTIVE_ROLE: carry.active_role,
        CLAIM_TENANT: user.tenant_id,
        CLAIM_SIGNED_IN_WITH_PASSKEY: carry.signed_in_with_passkey,
        **_federation_claims(carry.federated_login),
    }
    if refresh_session_id is not None:
        claims[CLAIM_REFRESH_SESSION] = refresh_session_id
    return claims


def _access_token(
    user: User,
    carry: SessionCarryOver,
    base_claims: dict[str, object],
    scopes: list[str] | None = None,
) -> str:
    """Even when ``scopes`` is given, trim it to the intersection with the active role's
    permissions. Logins pending two-factor enrollment get no permissions."""
    granted = user.permission_codes_of(carry.active_role)
    setup_required = needs_two_factor_setup(user, carry)
    effective = [] if setup_required else sorted(granted if scopes is None else granted & set(scopes))
    issued_at = base_claims["iat"]
    if not isinstance(issued_at, datetime):  # pragma: no cover - _base_claims always sets a datetime
        raise TypeError("iat must be a datetime")
    return jwt.encode(
        {
            **base_claims,
            "type": TYPE_ACCESS,
            "scope": effective,
            "email": user.email,
            # ⚠ **Verification doesn't hit the DB, so everything the principal needs goes here**
            #   (ADR-0076 §5). A forgotten item would be empty only on that path.
            "username": user.username,
            CLAIM_TWO_FACTOR_SETUP: setup_required,
            "exp": issued_at + timedelta(seconds=settings.access_token_expires_seconds),
        },
        settings.jwt_secret_key,
        algorithm=_ALGORITHM,
    )


def _logout_token(user: User, refresh_session_id: str, issued_at: datetime, expires_at: datetime) -> str:
    """A token that can do nothing but end the login (ADR-0091)."""
    return jwt.encode(
        {
            "sub": str(user.id),
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
            "iat": issued_at,
            "exp": expires_at,
            "type": TYPE_LOGOUT,
            CLAIM_REFRESH_SESSION: refresh_session_id,
        },
        settings.jwt_secret_key,
        algorithm=_ALGORITHM,
    )


def create_machine_access_token(user: User, *, client_id: str, operations: frozenset[str]) -> MachineAccessToken:
    """Access token for the machine endpoint (ADR-0087). **No refresh token** (machines just request
    a new one).

    Scopes are **only those in both** "the permissions of all the user's roles" and "the
    allowlisted operations".
    ⚠ ``auth_time`` is set to "long ago" (machines cannot pass operations requiring a recent
    sign-in; ADR-0076 §10).
    """
    effective = sorted(user.permission_codes_of(None) & operations)
    now = utcnow_aware()
    token = jwt.encode(
        {
            "sub": str(user.id),
            "iss": settings.access_token_issuer,
            "aud": settings.access_token_audience,
            "iat": now,
            "exp": now + timedelta(seconds=settings.access_token_expires_seconds),
            "type": TYPE_ACCESS,
            "scope": effective,
            "email": user.email,
            "username": user.username,
            CLAIM_AUTHENTICATED_AT: int(SIGNED_IN_LONG_AGO.timestamp()),
            CLAIM_ACTIVE_ROLE: None,
            CLAIM_TENANT: user.tenant_id,
            CLAIM_MACHINE_CLIENT: client_id,
        },
        settings.jwt_secret_key,
        algorithm=_ALGORITHM,
    )
    return MachineAccessToken(token=token, expires_in=settings.access_token_expires_seconds, scopes=effective)


def _federation_claims(federated_login: FederatedLogin | None) -> dict[str, object]:
    """Copy the IdP-side session into claims. Nothing is added for local logins."""
    if federated_login is None:
        return {}
    claims: dict[str, object] = {
        CLAIM_FEDERATED_ISSUER: federated_login.session.issuer,
        CLAIM_FEDERATED_SUBJECT: federated_login.session.subject,
        CLAIM_FEDERATED_ISSUED_AT: _to_microseconds(federated_login.started_at),
    }
    if federated_login.session.session_id is not None:
        claims[CLAIM_SESSION_ID] = federated_login.session.session_id
    return claims


def _federated_login_of(claims: dict[str, Any]) -> FederatedLogin | None:
    """Read the IdP-side session from claims. ``None`` if absent."""
    issuer = claims.get(CLAIM_FEDERATED_ISSUER)
    subject = claims.get(CLAIM_FEDERATED_SUBJECT)
    started_at = claims.get(CLAIM_FEDERATED_ISSUED_AT)
    if not isinstance(issuer, str) or not isinstance(subject, str) or not isinstance(started_at, int):
        return None
    session_id = claims.get(CLAIM_SESSION_ID)
    return FederatedLogin(
        session=FederatedSession(
            issuer=issuer,
            subject=subject,
            session_id=session_id if isinstance(session_id, str) else None,
        ),
        started_at=_from_microseconds(started_at),
    )


def _to_microseconds(moment: datetime) -> int:
    """Naive UTC to microseconds since the epoch (CLAUDE.md "time contract")."""
    return int(moment.replace(tzinfo=UTC).timestamp() * 1_000_000)


def _from_microseconds(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000, UTC).replace(tzinfo=None)


def _session_revoked(claims: dict[str, Any], session: Session) -> bool:
    """Whether this token's session has ended.

    It has ended in four cases: the user ended earlier logins, e.g. by changing the password
    (ADR-0076 §8) / it was terminated at the IdP (ADR-0077 §3) / logged out or reuse was detected
    (ADR-0091) / the record's expiry has passed (ADR-0101).
    """
    if _issued_before_sessions_ended(claims, session) or _refresh_session_ended(claims, session):
        return True
    check = CheckSessionRevocation(revocations=SqlSessionRevocationRepository(session))
    return check.execute(_federated_login_of(claims))


def _refresh_session_ended(claims: dict[str, Any], session: Session) -> bool:
    """Whether the login record is gone or past its expiry (ADR-0091, 0101). Tokens without a record
    are not stopped here.

    ⚠ **Expiry is checked here too.** Access tokens live a little past the record's expiry, so
    without this, repeated role switches would keep reissuing and break the non-sliding expiry.
    """
    refresh_session_id = claims.get(CLAIM_REFRESH_SESSION)
    if not isinstance(refresh_session_id, str):
        return False
    row = session.get(RefreshSession, refresh_session_id)
    return row is None or refresh_sessions.has_expired(row)


def _issued_before_sessions_ended(claims: dict[str, Any], session: Session) -> bool:
    """Whether the token was issued before the user's boundary (``user_session_boundaries``)
    (ADR-0076 §8).

    ``iat`` only has seconds, so the boundary is truncated to seconds for comparison. Rounding up
    would also reject **one's own token reissued within the same second** right after the
    boundary. Old tokens issued within that same second pass, but that window is under 1 second.
    """
    try:
        user = session.get(User, int(claims.get("sub", "")))
    except ValueError:
        return True
    if user is None or user.sessions_valid_from is None:
        return False
    issued_at = claims.get("iat")
    if not isinstance(issued_at, int):
        return True
    return issued_at < int(user.sessions_valid_from.replace(tzinfo=UTC).timestamp())


def _authenticated_at_of(claims: dict[str, Any]) -> datetime:
    """Time the user last actually signed in. Missing or unreadable means "long ago" (ADR-0076 §10).

    ⚠ **Never default a missing value to "now".** Otherwise a token from before this mechanism
    would turn into "just signed in again" after a single refresh.
    """
    value = claims.get(CLAIM_AUTHENTICATED_AT)
    if not isinstance(value, int):
        return SIGNED_IN_LONG_AGO
    return datetime.fromtimestamp(value, UTC)


def _tenant_of(claims: dict[str, Any]) -> int | None:
    value = claims.get(CLAIM_TENANT)
    return value if isinstance(value, int) else None


def _machine_client_of(claims: dict[str, Any]) -> str | None:
    value = claims.get(CLAIM_MACHINE_CLIENT)
    return value if isinstance(value, str) and value else None


def _active_role_of(claims: dict[str, Any]) -> str | None:
    """The active role from the claim. Missing or non-string means "all roles".

    Already-issued tokens without the claim (from before this feature) keep working.
    """
    value = claims.get(CLAIM_ACTIVE_ROLE)
    return value if isinstance(value, str) else None


__all__ = [
    "CLAIM_ACTIVE_ROLE",
    "CLAIM_AUTHENTICATED_AT",
    "CLAIM_FEDERATED_ISSUED_AT",
    "CLAIM_FEDERATED_ISSUER",
    "CLAIM_FEDERATED_SUBJECT",
    "CLAIM_MACHINE_CLIENT",
    "CLAIM_REFRESH_SESSION",
    "CLAIM_SESSION_ID",
    "CLAIM_SIGNED_IN_WITH_PASSKEY",
    "CLAIM_TENANT",
    "CLAIM_TWO_FACTOR_SETUP",
    "SIGNED_IN_LONG_AGO",
    "TYPE_ACCESS",
    "TYPE_LOGOUT",
    "TYPE_REFRESH",
    "MachineAccessToken",
    "RefreshedSession",
    "TokenService",
    "create_machine_access_token",
]
