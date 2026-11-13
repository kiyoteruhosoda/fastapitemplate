"""FastAPI JWT authentication dependencies.

Verifies the JWT via ``Depends()`` and passes the verified ``AuthenticatedPrincipal`` to
routers. Authorization is declared with :func:`require_permission` (scope based).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.routing import Route

from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.kernel.database.session import get_db
from shared.kernel.logging.request_context import actor_user_id_var, user_id_hash_var
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow_aware

logger = logging.getLogger(__name__)

# Name of the cookie holding the access token (set by the auth router at login)
ACCESS_TOKEN_COOKIE = "access_token"
# Refresh token cookie. **Its path is limited to the refresh endpoint**: riding along on other
# requests would needlessly multiply how often a long-lived credential is sent (ADR-0076 §4).
REFRESH_TOKEN_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth/refresh"
# A token used only to end the login (ADR-0091). The refresh cookie's path is limited and doesn't
# reach the logout endpoint, and the access token cookie expires with its lifetime. This token can
# do nothing but end that login.
LOGOUT_TOKEN_COOKIE = "logout_token"
LOGOUT_COOKIE_PATH = "/api/auth/logout"


def set_access_token_cookie(response: Response, token: str, *, max_age: int | None = None) -> None:
    """Set the access token cookie.

    Several paths issue tokens (password, refresh, passkey), so the attributes are set in this
    one place. ``max_age`` defaults to the token lifetime (only SSO logins keep it longer;
    ADR-0104).
    """
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        max_age=settings.access_token_expires_seconds if max_age is None else max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


def set_refresh_token_cookie(response: Response, token: str, *, max_age: int) -> None:
    """Set the refresh token cookie (ADR-0076 §4).

    ⚠ **Not put in the response body.** Cookies are sent automatically, so returning it in the
    body too would let XSS call ``POST /api/auth/refresh`` and read the new token, making
    ``httpOnly`` meaningless.
    """
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def set_logout_token_cookie(response: Response, token: str, *, max_age: int) -> None:
    response.set_cookie(
        LOGOUT_TOKEN_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=LOGOUT_COOKIE_PATH,
    )


def clear_access_token_cookie(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    clear_refresh_cookies(response)


def clear_refresh_cookies(response: Response) -> None:
    """Drop the refresh and logout tokens (SSO logins don't have them; ADR-0104)."""
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(LOGOUT_TOKEN_COOKIE, path=LOGOUT_COOKIE_PATH)


# Authorization header first, falling back to the cookie
_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    access_token_cookie: str | None,
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return access_token_cookie or None


async def get_operation_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
) -> AuthenticatedPrincipal:
    """Verify the JWT and return an ``AuthenticatedPrincipal``. 401 on failure. **Machine principals
    pass too** (ADR-0087).

    ⚠ **Only scope-guarded gates use this directly** (:func:`require_permission` /
    :func:`require_any_permission` and the dependency that extracts the principal's tenant).
    Tokens issued to machines have scopes limited to the operations in their allowlist, so
    scope-guarded endpoints may let them through. Other endpoints use
    :func:`get_current_principal` (humans only).

    ⚠ **Does not hit the DB** (ADR-0076 §5). Everything needed for authorization is in the token
    claims. Paths that need the user row itself use :func:`get_current_user`, which loads one
    row but **is not an authorization decision**.
    """
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal, reason = TokenService.verify_access_token_with_reason(token)
    if not principal:
        logger.debug("JWT authentication failed: %s", reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "reason": reason},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Propagate user.id_hash to subsequent logs (no PII is kept)
    user_id_hash_var.set(principal.id_hash)
    # The audit log's "who", so it can be recorded without callers passing the principal around
    actor_user_id_var.set(principal.user_id)
    return principal


MACHINE_NOT_ALLOWED = "machine_not_allowed"
TWO_FACTOR_SETUP_REQUIRED = "two_factor_setup_required"
#: Endpoints open to logins pending two-factor enrollment (ADR-0093). Refresh and logout don't
#: look at the principal, so they pass without being listed here.
_OPEN_DURING_TWO_FACTOR_SETUP = frozenset(
    {
        ("GET", "/api/auth/me"),
        ("GET", "/api/account/security/two-factor"),
        ("POST", "/api/account/security/two-factor/enrollment"),
        ("POST", "/api/account/security/two-factor/confirmation"),
    }
)


async def get_current_principal(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_operation_principal),
) -> AuthenticatedPrincipal:
    """Return a human principal. **Machine principals get 403** (ADR-0087 decision 4).

    Endpoints not guarded by a scope (own settings, role switching, credential changes, etc.)
    can't be limited by allowlisted operations. Opening them to machines would let them do
    anything as the user they act for, so they are refused by default and only scope-guarded
    endpoints are opened.
    """
    if principal.is_machine:
        refuse_machine(principal, _operation_of(request))
    if (request.method, request.url.path) not in _OPEN_DURING_TWO_FACTOR_SETUP:
        refuse_during_two_factor_setup(principal)
    return principal


def refuse_during_two_factor_setup(principal: AuthenticatedPrincipal) -> None:
    """Reject logins pending two-factor enrollment (ADR-0093). This 403 switches the UI to the
    enrollment screen."""
    if principal.two_factor_setup_required:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TWO_FACTOR_SETUP_REQUIRED})


def refuse_machine(principal: AuthenticatedPrincipal, operation: str) -> NoReturn:
    """Reject machine principals (human-only endpoints). Audit, then 403."""
    _refuse_machine(principal, operation, "person_only")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": MACHINE_NOT_ALLOWED})


def _operation_of(request: Request) -> str:
    """Operation name for the audit (a route template like ``GET /api/items``; URLs with values
    are not recorded)."""
    route = request.scope.get("route")
    path = route.path if isinstance(route, Route) else request.url.path
    return f"{request.method} {path}"


def _record_machine_write(principal: AuthenticatedPrincipal, request: Request) -> None:
    """Audit write operations by machines (which machine, as whom, what; ADR-0087). Read-only
    operations are not recorded."""
    if not principal.is_machine or request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    from bounded_contexts.audit.domain.entities.audit_event import AuditEventType, AuditResult
    from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
    from bounded_contexts.audit.presentation.dependencies import record_audit_event

    route = request.scope.get("route")
    path = route.path if isinstance(route, Route) else request.url.path
    record_audit_event().as_actor(principal.user_id).execute(
        AuditEventType.MACHINE_OPERATION_PERFORMED,
        AuditResult.SUCCESS,
        target=AuditTarget.of(AuditTargetType.MACHINE_CLIENT, principal.machine_client_id),
        reason=f"{request.method} {path}",
    )


def _refuse_machine(principal: AuthenticatedPrincipal, operation: str, why: str) -> None:
    """Audit a refused machine operation (ADR-0087 decision 5; ``client_id``, operation, reason)."""
    from bounded_contexts.audit.domain.entities.audit_event import AuditEventType, AuditResult
    from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget, AuditTargetType
    from bounded_contexts.audit.presentation.dependencies import record_audit_event

    logger.info("machine_operation_refused", extra={"client_id": principal.machine_client_id, "reason": why})
    record_audit_event().as_actor(principal.user_id).execute(
        AuditEventType.MACHINE_OPERATION_REFUSED,
        AuditResult.FAILURE,
        target=AuditTarget.of(AuditTargetType.MACHINE_CLIENT, principal.machine_client_id),
        reason=f"{why}: {operation}",
    )


def _refuse_missing_operation(principal: AuthenticatedPrincipal, codes: tuple[str, ...]) -> None:
    """Audit a machine operation lacking scope. The reason is "not in the allowlist" or "not in
    the user's roles"."""
    from bounded_contexts.identity_federation.domain.value_objects.machine_client import (
        find_machine_client,
        parse_machine_clients,
    )

    client = find_machine_client(parse_machine_clients(settings.machine_clients), principal.machine_client_id or "")
    missing = [code for code in codes if not principal.can(code)]
    outside = [code for code in missing if client is None or not client.allows(code)]
    why = "not_in_allowlist" if outside else "role_lacks_permission"
    _refuse_machine(principal, ",".join(missing), why)


def get_current_user(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> User:
    """Return the ``User`` row for the authenticated principal.

    Use only when "current state not carried in the token" is needed, such as the role list
    (authorization is decided by scopes in :func:`require_permission`).
    """
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    return user


def get_current_user_or_none(
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: Session = Depends(get_db),
) -> User | None:
    """Return the user if signed in, ``None`` otherwise (no 401).

    ⚠ **Don't use this for authorization.** It is only for paths reached by **browser
    navigation** (the federation return in ADR-0077 §5). A 401 there would show the user a raw
    JSON string with no way to retry. Endpoints that need authorization use the
    :func:`get_current_principal` family.
    """
    from presentation.fastapi.services.token_service import TokenService

    if not access_token_cookie:
        return None
    principal, _ = TokenService.verify_access_token_with_reason(access_token_cookie)
    if principal is None:
        return None
    return db.get(User, principal.user_id)


@dataclass(frozen=True)
class CurrentSession:
    """The user currently operating, and their entrance (ADR-0077 §3).

    ``federated_login`` of ``None`` means a local login. Endpoints that reissue tokens (role
    switch) **carry this over unchanged**.
    """

    user: User
    federated_login: FederatedLogin | None
    #: Current active role (ADR-0078 §1). Carried over on reissue.
    active_role: str | None = None
    #: Time the user last actually signed in (ADR-0076 §10). Carried over on reissue.
    authenticated_at: datetime | None = None
    #: This login's record (ADR-0091). Carried over on role switch.
    refresh_session_id: str | None = None
    #: Whether the login used a passkey (ADR-0093). Carried over on reissue.
    signed_in_with_passkey: bool = False


def get_current_session(
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: Session = Depends(get_db),
) -> CurrentSession:
    """Return the authenticated user and where the session started.

    The token was already verified by :func:`get_current_principal` (same value in the same
    request). Only the subject claims are read here; authentication is not redone.

    ⚠ **This exists for paths that "issue new tokens"** (role switch). Since access token
    verification no longer hits the DB (ADR-0076 §5), **reissue paths alone check the user is
    not suspended**: otherwise a suspended user could **keep receiving new tokens forever** just
    by switching repeatedly. **The lifetime bound would break there.**
    """
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)
    if token and TokenService.session_is_revoked(token, session=db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "reason": "session_revoked"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal, _ = TokenService.verify_access_token_with_reason(token or "")
    return CurrentSession(
        user=user,
        federated_login=TokenService.federated_login_of(token) if token else None,
        active_role=principal.active_role if principal is not None else None,
        authenticated_at=principal.authenticated_at if principal is not None else None,
        refresh_session_id=TokenService.refresh_session_id_of(token) if token else None,
        signed_in_with_passkey=TokenService.signed_in_with_passkey_of(token) if token else False,
    )


def get_settled_principal(
    # ⚠ **The value is unused; it is only here to pass the gate** (the ``_`` prefix marks that).
    _session: CurrentSession = Depends(get_current_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
) -> AuthenticatedPrincipal:
    """Gate for **paths that change credentials** (ADR-0076 §5 decision 6).

    Enrolling or removing two-factor auth or passkeys "creates a new entrance".
    ⚠ **Since access token verification no longer hits the DB, a suspended user's token in hand
    stays valid until it expires.** Letting that token create a new entrance would half defeat
    the suspension, so here alone the current state is checked before passing.

    The check is :func:`get_current_session` (the user is active and not suspended at the IdP).
    **The same gate as the reissue paths** is used.
    """
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)
    principal, _ = TokenService.verify_access_token_with_reason(token or "")
    if principal is None:  # pragma: no cover - always readable once the gate is passed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    return principal


REAUTHENTICATION_REQUIRED = "reauthentication_required"


def ensure_recent_sign_in(principal: AuthenticatedPrincipal) -> None:
    """Before **operations that change the entrance itself**, check the user just signed in again
    (ADR-0076 §10).

    Adding a passkey or changing the email with a stolen session would allow continued access
    without password or second factor. Unless within ``RECENT_SIGN_IN_SECONDS`` of the last
    actual sign-in, reject with 403 and the UI sends the user to sign in again.
    It applies equally to users without a password (SSO only).
    """
    signed_in_at = principal.authenticated_at
    limit = timedelta(seconds=settings.recent_sign_in_seconds)
    if signed_in_at is None or utcnow_aware() - signed_in_at > limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": REAUTHENTICATION_REQUIRED},
        )


async def require_recent_sign_in(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """:func:`ensure_recent_sign_in` applied as a gate (dependency)."""
    ensure_recent_sign_in(principal)
    return principal


def require_permission(*codes: str) -> Callable[..., Awaitable[AuthenticatedPrincipal]]:
    """Dependency factory that allows access only if all the given permissions are held.

    Example::

        @router.get("/api/admin/users")
        def list_users(
            principal: AuthenticatedPrincipal = Depends(require_permission("user:manage")),
        ):
            ...
    """

    async def _check(
        request: Request,
        principal: AuthenticatedPrincipal = Depends(get_operation_principal),
    ) -> AuthenticatedPrincipal:
        refuse_during_two_factor_setup(principal)
        if not principal.can(*codes):
            if principal.is_machine:
                _refuse_missing_operation(principal, codes)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"Required permissions: {', '.join(codes)}",
                },
            )
        _record_machine_write(principal, request)
        return principal

    return _check


def require_any_permission(*codes: str) -> Callable[..., Awaitable[AuthenticatedPrincipal]]:
    """Allow access if **any one** of the given permissions is held.

    Used when reasons to read a resource span several duties (the role list is needed both to
    "manage roles" and to "assign roles to users"; ADR-0078 §2).
    **Not for writes**: granting sides state a single scope explicitly.
    """

    async def _check(
        request: Request,
        principal: AuthenticatedPrincipal = Depends(get_operation_principal),
    ) -> AuthenticatedPrincipal:
        refuse_during_two_factor_setup(principal)
        if not any(principal.can(code) for code in codes):
            if principal.is_machine:
                _refuse_missing_operation(principal, codes)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"Required one of: {', '.join(codes)}",
                },
            )
        _record_machine_write(principal, request)
        return principal

    return _check


__all__ = [
    "ACCESS_TOKEN_COOKIE",
    "LOGOUT_COOKIE_PATH",
    "LOGOUT_TOKEN_COOKIE",
    "MACHINE_NOT_ALLOWED",
    "REAUTHENTICATION_REQUIRED",
    "REFRESH_COOKIE_PATH",
    "REFRESH_TOKEN_COOKIE",
    "TWO_FACTOR_SETUP_REQUIRED",
    "CurrentSession",
    "clear_access_token_cookie",
    "clear_refresh_cookies",
    "ensure_recent_sign_in",
    "get_current_principal",
    "get_current_session",
    "get_current_user",
    "get_operation_principal",
    "refuse_during_two_factor_setup",
    "refuse_machine",
    "require_any_permission",
    "require_permission",
    "require_recent_sign_in",
    "set_access_token_cookie",
    "set_logout_token_cookie",
    "set_refresh_token_cookie",
]
