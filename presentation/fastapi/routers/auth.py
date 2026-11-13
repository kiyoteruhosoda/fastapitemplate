"""Authentication API (login, token refresh, password change / reset).

Authentication results are also recorded in the audit log (``audit_log``). Failed login attempts
are recorded with ``result=failure``, with a "why it failed" category in ``reason``
(passwords and email addresses themselves are never recorded; ADR-0075 §1).

Login credential verification itself belongs to
:class:`~presentation.fastapi.services.login_service.LoginService`. This module only handles the
HTTP concern of putting the result into tokens and cookies.

Logout is not recorded: it is an unauthenticated endpoint that only drops cookies, and the user
cannot be identified.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from bounded_contexts.account_security.application.use_cases.throttle_login import ThrottleLogin
from bounded_contexts.account_security.domain.entities.login_attempts import PURPOSE_PASSWORD_RESET
from bounded_contexts.account_security.presentation import dependencies as security
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from presentation.fastapi.dependencies.auth import (
    LOGOUT_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    CurrentSession,
    clear_access_token_cookie,
    clear_refresh_cookies,
    ensure_recent_sign_in,
    get_current_principal,
    get_current_session,
    get_current_user,
)
from presentation.fastapi.dependencies.local_login import require_local_login
from presentation.fastapi.dependencies.login import LoginServiceDep
from presentation.fastapi.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    ProfileUpdateRequest,
    ResetPasswordRequest,
    RoleSwitchRequest,
    SessionResponse,
    StatusResponse,
)
from presentation.fastapi.services import refresh_sessions
from presentation.fastapi.services.password_reset_service import PasswordResetService
from presentation.fastapi.services.refresh_sessions import RefreshStanding
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from presentation.fastapi.services.session_cookies import establish_session
from presentation.fastapi.services.token_service import TokenService
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.infrastructure.models import User
from shared.infrastructure.sign_in_directory import email_taken
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings
from shared.kernel.timestamps import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

DbDep = Annotated[Session, Depends(get_db)]
PrincipalDep = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentSessionDep = Annotated[CurrentSession, Depends(get_current_session)]


def _me_response(user: User, principal: AuthenticatedPrincipal, *, profile_managed_by_idp: bool) -> MeResponse:
    """The caller's own info. scopes are "currently effective", roles are "switchable to"."""
    return MeResponse(
        user_id=user.id,
        email=user.email,
        username=user.username,
        scopes=sorted(principal.permissions),
        roles=list(user.role_names),
        active_role=principal.active_role,
        has_password=user.has_local_password,
        rp_logout_enabled=settings.oidc_rp_logout_enabled,
        profile_managed_by_idp=profile_managed_by_idp,
        two_factor_setup_required=principal.two_factor_setup_required,
    )


@router.post("/login", response_model=SessionResponse, dependencies=[Depends(require_local_login)])
def login(body: LoginRequest, response: Response, login_service: LoginServiceDep) -> SessionResponse:
    """Password authentication. ``totp_code`` is also required if two-factor auth is enabled."""
    user = login_service.authenticate(body)
    logger.info("login_succeeded")
    return establish_session(response, user)


@router.post("/refresh", response_model=SessionResponse)
def refresh(
    response: Response,
    db: DbDep,
    audit: AuditRecorderDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)] = None,
) -> SessionResponse | JSONResponse:
    """Refresh tokens. The active role (ADR-0078 §1) carries over.

    Refresh tokens of SSO logins are not accepted (ADR-0104).

    If an already-used token comes back, only that login is ended (ADR-0091).

    ⚠ **Tokens are not accepted in the body** (ADR-0076 §4). Keeping such an endpoint would give
    the SPA a reason to keep holding tokens.
    """
    refreshed = TokenService.verify_refresh_token(refresh_token or "", session=db)
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    if refreshed.standing == RefreshStanding.REUSED:
        refresh_sessions.end(db, refreshed.refresh_session_id)
        # Leaving with 401 rolls back the request's session, so commit the termination here
        db.commit()
        logger.warning("refresh_token_reused")
        audit.execute(
            AuditEventType.REFRESH_TOKEN_REUSED,
            AuditResult.FAILURE,
            target=AuditTarget.of(AuditTargetType.USER, refreshed.user.id),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid_token"})
    if refreshed.federated_login is not None:
        # SSO logins are not refreshed (ADR-0104). Reject even refresh tokens issued before this
        # mechanism: the point is to stop use of stolen cookies, and if not stopped here they
        # would last 14 days
        return _refuse_federated_refresh(db, refreshed.refresh_session_id)
    # A refresh is not a re-sign-in. The time of the last actual sign-in carries over too
    # (ADR-0076 §10)
    return establish_session(response, refreshed.user, refreshed.carry)


def _refuse_federated_refresh(db: Session, refresh_session_id: str) -> JSONResponse:
    """Reject an SSO login's refresh token and delete the record and token. The UI asks the IdP again.

    Returns a response instead of raising, so the 401 can carry the ``Set-Cookie`` that drops
    the token.
    """
    refresh_sessions.end(db, refresh_session_id)
    response = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": {"error": "invalid_token"}})
    clear_refresh_cookies(response)
    return response


@router.post("/logout", response_model=StatusResponse)
def logout(
    response: Response,
    db: DbDep,
    logout_token: Annotated[str | None, Cookie(alias=LOGOUT_TOKEN_COOKIE)] = None,
) -> StatusResponse:
    """End only this login (other devices continue; ADR-0091)."""
    if logout_token:
        TokenService.end_refresh_session(logout_token, session=db)
        # Like rotation, don't hold the row lock until the response (session_cookies.py)
        db.commit()
    clear_access_token_cookie(response)
    return StatusResponse(status="ok")


@router.get("/me", response_model=MeResponse)
def me(principal: PrincipalDep, user: CurrentUserDep, db: DbDep) -> MeResponse:
    return _me_response(user, principal, profile_managed_by_idp=SqlFederatedIdentityRepository(db).is_linked(user.id))


@router.post("/switch-role", response_model=SessionResponse)
def switch_role(
    body: RoleSwitchRequest,
    response: Response,
    current: CurrentSessionDep,
    audit: AuditRecorderDep,
) -> SessionResponse:
    """Switch the active role and issue new tokens (ADR-0078 §1).

    If ``role`` is ``null``, revert to "all roles" (union of held permissions).
    You cannot switch to a role you don't hold (permissions never increase).

    ⚠ **The entrance (IdP session) carries over unchanged** (ADR-0077 §3).
    """
    user = current.user
    if body.role is not None and body.role not in user.role_names:
        audit.execute(AuditEventType.ROLE_SWITCHED, AuditResult.FAILURE, reason="role_not_granted")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "role_not_granted"})

    session = establish_session(
        response,
        user,
        SessionCarryOver(
            active_role=body.role,
            federated_login=current.federated_login,
            authenticated_at=current.authenticated_at,
            refresh_session_id=current.refresh_session_id,
            signed_in_with_passkey=current.signed_in_with_passkey,
        ),
    )
    audit.execute(AuditEventType.ROLE_SWITCHED, reason=f"role={body.role or 'all'}")
    logger.info("active_role_switched")
    return session


@router.put("/me", response_model=MeResponse)
def update_me(
    body: ProfileUpdateRequest,
    principal: PrincipalDep,
    db: DbDep,
    audit: AuditRecorderDep,
) -> MeResponse:
    """Change the caller's own email address and display name (ADR-0080 §3).

    The audit log ``reason`` holds only the names of changed fields, never the values
    (email address, display name) (ADR-0075 §1).
    """
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error": "invalid_token"})
    if SqlFederatedIdentityRepository(db).is_linked(user.id):
        # Overwritten by the IdP's values on every login, so accepting it would silently revert
        # (ADR-0094)
        if (body.email, body.username) != (user.email, user.username):
            audit.execute(AuditEventType.PROFILE_UPDATED, AuditResult.FAILURE, reason="profile_managed_by_idp")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "profile_managed_by_idp"})
        return _me_response(user, principal, profile_managed_by_idp=True)
    if body.email != user.email:
        # The email is where reset emails go. Change it only right after re-signing in
        # (ADR-0076 §10)
        ensure_recent_sign_in(principal)
    if email_taken(db, body.email, user.tenant_id, except_user_id=user.id):
        audit.execute(AuditEventType.PROFILE_UPDATED, AuditResult.FAILURE, reason="email_already_exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "email_already_exists"})

    changed = sorted(
        name
        for name, new, old in (("email", body.email, user.email), ("username", body.username, user.username))
        if new != old
    )
    user.email = body.email
    user.username = body.username
    try:
        # A prior SELECT can't see a concurrent update (TOCTOU). Settle any unique constraint
        # violation here before queuing the success audit (failing after queuing would leave a
        # success audit for an update that was rolled back).
        db.flush()
    except IntegrityError:
        audit.execute(AuditEventType.PROFILE_UPDATED, AuditResult.FAILURE, reason="email_already_exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "email_already_exists"}) from None
    audit.execute(AuditEventType.PROFILE_UPDATED, reason=f"fields={','.join(changed) if changed else 'none'}")
    return _me_response(user, principal, profile_managed_by_idp=False)


@router.post("/change-password", response_model=StatusResponse, dependencies=[Depends(require_local_login)])
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    current: CurrentSessionDep,
    audit: AuditRecorderDep,
) -> StatusResponse:
    """Change the password and **end other logins that started before it** (ADR-0076 §8).

    The goal is to stop stolen refresh tokens, so only this session of the person who changed it
    continues with newly issued tokens (role and entrance carry over).
    """
    user = current.user
    if user.password_hash is None or not check_password_hash(user.password_hash, body.current_password):
        # ⚠ **Users without a password are rejected here too** (ADR-0076 §6), with no distinct
        # reason: revealing "has none" would let outsiders count who has which entrances.
        audit.execute(
            AuditEventType.PASSWORD_CHANGED,
            AuditResult.FAILURE,
            reason="invalid_current_password",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_current_password"},
        )
    user.password_hash = generate_password_hash(body.new_password)
    user.end_sessions()
    # The current password was just verified, so treat it as a re-sign-in (ADR-0076 §10)
    establish_session(
        response,
        user,
        SessionCarryOver(
            active_role=current.active_role,
            federated_login=current.federated_login,
            signed_in_with_passkey=current.signed_in_with_passkey,
            # The row is recreated, but a non-sliding lifetime is not extended (ADR-0101)
            lifetime_from_session_id=current.refresh_session_id,
        ),
    )
    logger.info("password_changed")
    audit.execute(AuditEventType.PASSWORD_CHANGED)
    return StatusResponse(status="ok")


@router.post("/forgot-password", response_model=StatusResponse, dependencies=[Depends(require_local_login)])
def forgot_password(
    body: ForgotPasswordRequest,
    db: DbDep,
    audit: AuditRecorderDep,
    throttle: Annotated[ThrottleLogin, Depends(security.throttle_login)],
) -> StatusResponse:
    """Send a reset link.

    This endpoint is unauthenticated, so the audit log records the requested account as the
    **target** and leaves the actor empty. Anyone who knows the email address can call it, so
    recording the owner as actor would look like their own action (ADR-0075 §1).
    """
    # Count per identifier. **Successes count too**: a success still sends an email, so without
    # counting, knowing the address would be enough to flood the inbox (ADR-0076 §9)
    throttle.require_allowed(PURPOSE_PASSWORD_RESET, body.email, utcnow())
    throttle.record_attempt(PURPOSE_PASSWORD_RESET, body.email, utcnow())
    # Same response whether or not the user exists (against enumeration attacks)
    user_id = PasswordResetService().request_reset(db, body.email, body.tenant)
    audit.execute(
        AuditEventType.PASSWORD_RESET_REQUESTED,
        AuditResult.SUCCESS if user_id is not None else AuditResult.FAILURE,
        target=AuditTarget.of(AuditTargetType.USER, user_id) if user_id is not None else None,
        reason=None if user_id is not None else "unknown_email",
    )
    return StatusResponse(status="accepted")


@router.post("/reset-password", response_model=StatusResponse, dependencies=[Depends(require_local_login)])
def reset_password(body: ResetPasswordRequest, db: DbDep, audit: AuditRecorderDep) -> StatusResponse:
    """Set a new password using a token.

    This is also unauthenticated (only the token is presented), so record as target with an
    empty actor.
    """
    user_id = PasswordResetService().reset(db, body.token, body.new_password)
    if user_id is None:
        audit.execute(
            AuditEventType.PASSWORD_RESET_COMPLETED,
            AuditResult.FAILURE,
            reason="invalid_or_expired_token",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_or_expired_token"},
        )
    audit.execute(
        AuditEventType.PASSWORD_RESET_COMPLETED,
        target=AuditTarget.of(AuditTargetType.USER, user_id),
    )
    return StatusResponse(status="ok")
