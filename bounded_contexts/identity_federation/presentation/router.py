"""SSO (OpenID Connect) login API.

There are 12 routes.

- ``GET /provider`` — tells the login screen whether to show the "Sign in with SSO" button
- ``GET /login`` — sends the browser to the IdP's authorization endpoint
  (with ``?prompt=none``, tries without showing a screen)
- ``GET /renew`` — starts the round trip that silently continues an expired login
  (inside a hidden frame. ADR-0104)
- ``GET /callback`` — return from the IdP. Sends the user back to the SPA with a redemption ticket
  (for a renewal round trip, sets the cookies and goes to the result page)
- ``GET /renewed`` — the result page of the renewal round trip (the screen reads the frame's URL)
- ``POST /token`` — exchanges the redemption ticket for tokens (cookies are set here too)
- ``GET /logout`` — carries the sign-out through to the IdP (**disabled by default**)
- ``GET /signed-out`` — return from that. Just sends the user back to the login screen
- ``POST /backchannel-logout`` — receives logout notices from the IdP (ADR-0077 §3)
- ``GET /link`` — reports the caller's own link status (settings screen. ADR-0077 §5)
- ``POST /link/start`` — starts the linking round trip (pressed by the signed-in user)
- ``DELETE /link`` — removes the link

``/callback`` **serves both the login return and the link return**. Which follow-up runs is
decided by the round-trip state's ``purpose`` — to keep the redirect URI registered at the IdP
to a single one (ADR-0077 §5). ⚠ **Never pass the purpose in the query.** Rewriting the URL
would be enough to spoof it.

``/login`` **puts the round-trip state (``state`` / ``nonce`` / ``code_verifier``) into a signed
cookie before** redirecting, and ``/callback`` restores and checks it (ADR-0077 §1). The server
keeps no copy, so a party that only knows ``state`` cannot complete the return — even if a
victim is tricked into an authorization request started by an attacker, the victim's browser
has no matching cookie (login CSRF).

``/login`` and ``/callback`` are **browser navigations**; the SPA cannot read their response
bodies. So failures are returned as a redirect to the login screen (``?sso_error=<code>``)
rather than JSON.
The displayed wording is decided by the frontend (CLAUDE.md "Internationalization").

The redemption ticket that keeps tokens out of URLs is ADR-0077 §1.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated
from urllib.parse import parse_qsl, quote, urlencode

import jwt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from bounded_contexts.account_security.application.use_cases.count_local_factors import (
    CountLocalFactors,
)
from bounded_contexts.account_security.infrastructure.sql_local_factor_directory import (
    SqlLocalFactorDirectory,
)
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.identity_federation.application.dto.sso_dto import (
    ContinuedSessionDto,
    ResolvedAccountDto,
    SsoHandoffDto,
)
from bounded_contexts.identity_federation.application.use_cases.build_rp_logout_url import (
    BuildRpLogoutUrl,
)
from bounded_contexts.identity_federation.application.use_cases.describe_federated_link import (
    DescribeFederatedLink,
)
from bounded_contexts.identity_federation.application.use_cases.describe_sso_provider import (
    DescribeSsoProvider,
)
from bounded_contexts.identity_federation.application.use_cases.exchange_sso_ticket import (
    ExchangeSsoTicket,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_link import (
    StartSsoLink,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_login import (
    StartSsoLogin,
)
from bounded_contexts.identity_federation.application.use_cases.unlink_federated_identity import (
    UnlinkFederatedIdentity,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityFederationError,
    InvalidLogoutTokenError,
    SsoLinkSessionMismatchError,
    SsoLoginTransactionInvalidError,
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from bounded_contexts.identity_federation.domain.value_objects.sso_callback import (
    SsoCallback,
)
from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)
from bounded_contexts.identity_federation.presentation import dependencies, renewal, transaction_cookie
from bounded_contexts.identity_federation.presentation.schemas import (
    FederatedLinkResponse,
    SsoLinkStartResponse,
    SsoProviderResponse,
    SsoSessionResponse,
    SsoTicketRequest,
)
from presentation.fastapi.dependencies.auth import (
    ACCESS_TOKEN_COOKIE,
    get_current_user,
    get_current_user_or_none,
)
from presentation.fastapi.schemas.auth import StatusResponse
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from presentation.fastapi.services.session_cookies import establish_session
from presentation.fastapi.services.token_service import continuation_of
from shared.infrastructure.models import Tenant, User
from shared.infrastructure.tenant_directory import tenant_issuing
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]

# SPA routes to return to (keep in sync with the frontend routing)
LOGIN_SCREEN = "/login"
HANDOFF_SCREEN = "/login/sso"
#: Landing spot for the link return (security section of the settings screen. ADR-0077 §5)
SECURITY_SCREEN = "/profile/security"

# Error codes returned by the IdP go straight into the screen URL, so only well-formed ones pass
# (so a reflected string cannot be used to build links). Matching uses ``fullmatch`` —
# ``$`` also matches just before a trailing newline, so ``match`` would let a newline through.
_ERROR_CODE = re.compile(r"[a-z_]{1,64}")
_GENERIC_ERROR = "sso_error"

#: Codes the IdP returns on a silent attempt (``prompt=none``) meaning "a screen is required"
#: (OIDC Core §3.1.2.6). **Not a failure**, so return to the login screen without an error
#: (ADR-0077 §9).
#: ``access_denied`` is when the user is in Assay but not permitted to use this app (task #648).
_SILENT_DECLINES = frozenset(
    {
        "login_required",
        "consent_required",
        "interaction_required",
        "account_selection_required",
        "access_denied",
    }
)
#: Marker that we tried and came back. The login screen does not retry when it is present
#: (loop stopper).
SILENT_DECLINED_PARAM = "sso_silent"


class SsoCallbackQuery:
    """Query attached to the IdP's return (``code`` and ``state`` on success)."""

    def __init__(
        self,
        code: Annotated[str | None, Query(max_length=2048)] = None,
        state: Annotated[str | None, Query(max_length=255)] = None,
        error: Annotated[str | None, Query(max_length=255)] = None,
    ) -> None:
        self.code = code
        self.state = state
        self.error = error


@router.get("/provider", response_model=SsoProviderResponse)
def describe_provider(
    use_case: Annotated[DescribeSsoProvider, Depends(dependencies.describe_sso_provider)],
) -> SsoProviderResponse:
    """Answer whether SSO is available (callable unauthenticated; returns no connection details)."""
    provider = use_case.execute()
    return SsoProviderResponse(
        enabled=provider.enabled,
        display_name=provider.display_name,
        local_login_enabled=settings.local_login_enabled,
        rp_logout_enabled=provider.rp_logout_enabled,
    )


# ``/logout`` may send discovery to the IdP, so it is ``def`` (same reason as ``/login``).
@router.get("/logout", include_in_schema=False)
def logout(
    use_case: Annotated[BuildRpLogoutUrl, Depends(dependencies.build_rp_logout_url)],
    sec_fetch_site: Annotated[str | None, Header(alias="Sec-Fetch-Site")] = None,
) -> RedirectResponse:
    """Carry the sign-out through to the IdP. **Does not touch the app session here.**

    Ending it is the job of ``POST /api/auth/logout``; the screen does that first and then
    navigates here. Don't hold it in two places — they drift when only one side is fixed.

    **When it can't go through, just return to the login screen** (setting disabled, SSO
    unavailable, IdP doesn't publish ``end_session_endpoint``, called from elsewhere). Showing
    a failure here leaves the user nothing they can do.
    """
    if not _from_this_site(sec_fetch_site):
        logger.warning("sso_logout_rejected_cross_site")
        return _redirect(LOGIN_SCREEN)
    return _redirect(use_case.execute() or LOGIN_SCREEN)


def _from_this_site(sec_fetch_site: str | None) -> bool:
    """Check whether navigation to this route **started from our own site**.

    ⚠ **This endpoint changes state unauthenticated.** And what it changes is **the IdP's SSO
    session**, which is shared by every app using the same IdP. Unprotected, a foreign page could
    just place ``<img src="…/api/auth/sso/logout">`` and **lock the user out of other apps
    too** (the damage is only having to sign in again, but it is an unrequested side effect).

    ⚠ **Don't rely on the IdP's confirmation screen.** OIDC only says the OP *SHOULD* ask for
    confirmation when there is no ``id_token_hint``, and **our own idp (assay) doesn't**
    (implementation checked on 2026-09-07). This is the only safeguard.

    Looks at ``Sec-Fetch-Site``, set by the browser, rather than a cookie. No CSRF token
    because this is a **navigation** — carrying a token would mean building the URL in
    JavaScript, giving up the ability to open it with ``<a href>``.

    Allowed: navigation from our own origin (``same-origin``) and the user hitting it themselves
    (``none``: address bar, bookmark). **A missing header is also allowed** — browsers that omit
    it are old ones, and blocking them would make sign-out impossible. Navigations started from
    a foreign page **always carry it**, so the path we want to block is blocked.
    """
    return sec_fetch_site is None or sec_fetch_site in {"same-origin", "none"}


@router.get("/signed-out", include_in_schema=False)
def signed_out() -> RedirectResponse:
    """Landing spot after signing out at the IdP.

    **Register this URI on the IdP client** (``post_logout_redirect_uri``).
    If unregistered nothing breaks; it just stops at the IdP's own completion page.

    This is a separate route to **decouple the registered string from the SPA routing**.
    If changing a screen route meant fixing the IdP registration, one side would get fixed
    and the other would silently fall out of sync.
    """
    return _redirect(f"{LOGIN_SCREEN}?signed_out=1")


# ``/login`` and ``/callback`` make synchronous HTTP calls to the IdP (discovery, token exchange).
# As ``async def`` the event loop would block for that round trip and every request on the
# same worker would wait. Define them with ``def`` to offload to the thread pool.
@router.get("/login", include_in_schema=False)
def start_login(
    use_case: Annotated[StartSsoLogin, Depends(dependencies.start_sso_login)],
    tenant: dependencies.EntranceDep,
    redirect_to: Annotated[str | None, Query(max_length=255)] = None,
    # Ignore unknown values (this is a navigation, so don't show a 422 JSON)
    prompt: Annotated[str | None, Query(max_length=16)] = None,
) -> RedirectResponse:
    """Send to the IdP. Return to the login screen if unconfigured or the IdP is unreachable.

    The destination is the issuer of the tenant chosen at the entrance (``?tenant=<slug>``.
    ADR-0079 §1 decision 8).
    ``?prompt=none`` is added by the login screen itself when it opens (ADR-0077 §9). If signed in
    at the IdP, the user gets in without pressing the button; if not, they come back silently.
    """
    try:
        authorization = use_case.execute(redirect_to=redirect_to, silent=prompt == "none")
    except IdentityFederationError as error:
        logger.warning("sso_start_failed: %s", error.code)
        return _to_login_screen(error.code, _login_screen_of(tenant))
    response = RedirectResponse(url=authorization.authorization_url, status_code=status.HTTP_303_SEE_OTHER)
    transaction_cookie.issue(response, authorization.transaction, path=router.prefix)
    return response


def continued_session(
    access_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> ContinuedSessionDto | None:
    """Read the login to continue from the leftover expired token (``None`` if unreadable.
    ADR-0104)."""
    return continuation_of(access_token) if access_token else None


@router.get("/renew", include_in_schema=False)
def start_renewal(
    use_case: Annotated[StartSsoLogin, Depends(dependencies.start_sso_login)],
    continued: Annotated[ContinuedSessionDto | None, Depends(continued_session)],
) -> RedirectResponse:
    """Start the round trip that silently continues an expired login (ADR-0104).
    **The screen opens this in a hidden frame.**

    Always ``prompt=none``. If the IdP is unreachable, send to the result page (``failed``).
    """
    try:
        authorization = use_case.renew(continued)
    except IdentityFederationError as error:
        logger.warning("sso_renewal_start_failed: %s", error.code)
        return _renewal_result(renewal.RenewalResult.FAILED)
    response = RedirectResponse(url=authorization.authorization_url, status_code=status.HTTP_303_SEE_OTHER)
    transaction_cookie.issue(response, authorization.transaction, path=router.prefix)
    renewal.allow_same_origin_framing(response)
    return response


@router.get("/renewed", include_in_schema=False)
def renewal_result() -> Response:
    """Result page of the renewal round trip (the screen reads ``result`` from the frame URL)."""
    return renewal.result_page()


class _CallbackTools:
    """Tools needed for the callback follow-up.

    The login return and link return share one route, so both sets of tools are gathered here
    (to keep handler arguments few; same style as ``SsoCallbackQuery``).
    """

    def __init__(
        self,
        completion: Annotated[dependencies.SsoCompletion, Depends(dependencies.sso_completion)],
        audit: AuditRecorderDep,
        viewer: Annotated[User | None, Depends(get_current_user_or_none)] = None,
    ) -> None:
        self.completion = completion
        self.audit = audit
        self.viewer = viewer

    def login_screen(self, transaction: LoginTransaction | None) -> str:
        """Where to send failures. Back to the entrance of the tenant that started the round trip."""
        if transaction is None:
            return LOGIN_SCREEN
        return _login_screen_of(tenant_issuing(self.completion.db, transaction.issuer))


@router.get("/callback", include_in_schema=False)
def complete_callback(
    query: Annotated[SsoCallbackQuery, Depends()],
    tools: Annotated[_CallbackTools, Depends()],
    tx: Annotated[str | None, Cookie(alias=transaction_cookie.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Receive the return from the IdP. Serves both the login and the link return (ADR-0077 §5).

    The round-trip state cookie is dropped on success or failure (used up in one round trip).

    ⚠ **If the cookie can't be restored, treat it as a login return.** Whether it was a link
    is written only in that round-trip state (the result is a return to the login screen
    with ``sso_state_invalid``; retrying lets the link go through).
    """
    transaction = transaction_cookie.read(tx)
    if transaction is not None and transaction.purpose is TransactionPurpose.LINK:
        return _complete_link(query, tools, transaction)
    if transaction is not None and transaction.purpose is TransactionPurpose.RENEW:
        return _complete_renewal(query, tools, transaction)
    return _complete_login(query, tools, transaction)


def _complete_login(
    query: SsoCallbackQuery,
    tools: _CallbackTools,
    transaction: LoginTransaction | None,
) -> RedirectResponse:
    """Send back to the SPA with a redemption ticket.

    Accepts the connection of **the issuer written in the round-trip state** (not re-derived from
    the URL. ADR-0079 §4).
    """
    screen = tools.login_screen(transaction)
    if transaction is not None and transaction.silent and query.error in _SILENT_DECLINES:
        return _silently_declined(transaction, screen)
    if query.error is not None or not query.code or not query.state:
        return _failed(tools.audit, query.error or "sso_callback_invalid", screen)
    if transaction is None:
        return _failed(tools.audit, SsoLoginTransactionInvalidError.code, screen)
    try:
        handoff = tools.completion.login(transaction.issuer).execute(
            code=query.code, state=query.state, transaction=transaction
        )
    except IdentityFederationError as error:
        return _failed(tools.audit, error.code, screen)
    _record_success(tools.audit, handoff.account)
    return _redirect(f"{HANDOFF_SCREEN}?ticket={quote(handoff.ticket)}")


def _complete_renewal(
    query: SsoCallbackQuery,
    tools: _CallbackTools,
    transaction: LoginTransaction,
) -> RedirectResponse:
    """Return of the renewal round trip (ADR-0104). Set the cookies and go to the result page.

    "Not signed in" and "not permitted" are not failures (just a silent attempt), so not recorded.
    """
    if query.error is not None or not query.code or not query.state:
        if query.error not in _SILENT_DECLINES:
            logger.warning("sso_renewal_failed: %s", query.error or "sso_callback_invalid")
            return _renewal_result(renewal.RenewalResult.FAILED)
        logger.info("sso_renewal_declined")
        return _renewal_result(renewal.RenewalResult.DECLINED)
    try:
        handoff = tools.completion.login(transaction.issuer).execute(
            code=query.code, state=query.state, transaction=transaction
        )
    except IdentityFederationError as error:
        logger.warning("sso_renewal_failed: %s", error.code)
        return _renewal_result(renewal.RenewalResult.FAILED)
    return _continue_session(tools, handoff, transaction)


def _continue_session(tools: _CallbackTools, handoff: SsoHandoffDto, transaction: LoginTransaction) -> RedirectResponse:
    """Redeem the ticket on the spot and set tokens that carry over the continued login.

    ⚠ **Don't continue if a different person came back** (they signed in again as someone else
    at the IdP). The open screen belongs to the previous person, so return ``declined`` and make
    the screen start over from login.
    """
    db = tools.completion.db
    session = dependencies.exchange_sso_ticket(db).execute(ticket=handoff.ticket)
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return _renewal_result(renewal.RenewalResult.DECLINED)
    if transaction.user_id is not None and transaction.user_id != user.id:
        logger.info("sso_renewal_switched_user")
        return _renewal_result(renewal.RenewalResult.DECLINED)
    response = _renewal_result(renewal.RenewalResult.RENEWED)
    try:
        establish_session(response, user, _carry_of(transaction, session.login, user))
    except HTTPException:
        # Suspended tenant (ADR-0079 §1). The login screen shows the reason
        return _renewal_result(renewal.RenewalResult.DECLINED)
    _record_account_changes(tools.audit, handoff.account)
    logger.info("sso_renewal_succeeded")
    return response


def _carry_of(transaction: LoginTransaction, login: FederatedLogin, user: User) -> SessionCarryOver:
    """What to carry over from the continued login.
    
    Roles **only if still held** (otherwise all roles).
    """
    # Like the switch endpoint (``/api/auth/switch-role``), accept only held roles (no privilege gain)
    requested = transaction.active_role
    role = requested if requested in user.role_names else None
    return SessionCarryOver(
        active_role=role,
        federated_login=login,
        authenticated_at=transaction.authenticated_at,
        signed_in_with_passkey=transaction.signed_in_with_passkey,
    )


def _renewal_result(result: renewal.RenewalResult) -> RedirectResponse:
    """Send to the result page.
    
    Drops the round-trip cookie and marks the response as allowed only in our own frame.
    """
    response = _redirect(renewal.result_location(result))
    renewal.allow_same_origin_framing(response)
    return response


def _complete_link(
    query: SsoCallbackQuery,
    tools: _CallbackTools,
    transaction: LoginTransaction,
) -> RedirectResponse:
    """Bind the returning party to the user who started the round trip and return to settings.

    ⚠ **Don't re-decide by looking at the currently signed-in user.** Who to bind to was fixed
    when the round trip started (``user_id`` in the round-trip state). Here we only check
    "is that person still signed in", and refuse if it has changed.
    """
    viewer = tools.viewer
    if viewer is None:
        return _link_failed(SsoLinkSessionMismatchError.code)
    if query.error is not None or not query.code or not query.state:
        return _link_failed(query.error or "sso_callback_invalid")
    callback = SsoCallback(code=query.code, state=query.state, transaction=transaction)
    try:
        tools.completion.link(transaction.issuer).execute(callback=callback, user_id=viewer.id)
    except IdentityFederationError as error:
        logger.warning("sso_link_failed: %s", error.code)
        return _link_failed(error.code)
    tools.audit.as_actor(viewer.id).execute(AuditEventType.SSO_IDENTITY_LINKED)
    logger.info("sso_link_succeeded")
    return _redirect(f"{SECURITY_SCREEN}?sso_link=linked")


@router.post("/link/start", response_model=SsoLinkStartResponse)
def start_link(
    user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[StartSsoLink, Depends(dependencies.start_sso_link)],
    response: Response,
) -> SsoLinkStartResponse:
    """Start the linking round trip. **The screen navigates to this URL itself.**

    It's XHR instead of returning 303 so that ⚠ **it can return 401 to a caller whose
    authentication has expired.** Started as a navigation, an expired session would only show a
    raw JSON string with no way to retry.

    ⚠ **CSRF protection applies here.** It's a cookie-authenticated state change, so it falls
    under ``CsrfMiddleware`` and can't be triggered from foreign pages.
    """
    authorization = use_case.execute(user_id=user.id)
    transaction_cookie.issue(response, authorization.transaction, path=router.prefix)
    return SsoLinkStartResponse(authorization_url=authorization.authorization_url)


@router.get("/link", response_model=FederatedLinkResponse)
def describe_link(
    user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[DescribeFederatedLink, Depends(dependencies.describe_federated_link)],
    db: DbDep,
) -> FederatedLinkResponse:
    """Report the caller's own link status (ADR-0077 §5). Others' links are not visible."""
    link = use_case.execute(user_id=user.id)
    return FederatedLinkResponse(
        available=link.available,
        display_name=link.display_name,
        linked=link.linked,
        linked_at=link.linked_at,
        can_unlink=link.linked and _has_other_entrance(db, user),
    )


@router.delete("/link", response_model=StatusResponse)
def remove_link(
    user: Annotated[User, Depends(get_current_user)],
    use_case: Annotated[UnlinkFederatedIdentity, Depends(dependencies.unlink_federated_identity)],
    audit: AuditRecorderDep,
    db: DbDep,
) -> StatusResponse:
    """Remove the link.
    
    ⚠ **Refuse users who could no longer sign in after removal** (ADR-0077 §5).
    """
    provider = dependencies.provider_of(db, user)
    if provider is None:
        raise SsoNotConfiguredError
    use_case.execute(
        issuer=provider.issuer,
        user_id=user.id,
        has_other_entrance=_has_other_entrance(db, user),
    )
    audit.as_actor(user.id).execute(AuditEventType.SSO_IDENTITY_UNLINKED)
    return StatusResponse(status="ok")


def _has_other_entrance(db: Session, user: User) -> bool:
    """Whether this user still has a **way in** after the IdP is removed.

    ⚠ **Two-factor authentication is not a way in.** It's a second factor behind the password,
    so it can't get you in on its own. What counts are passwords and passkeys.
    """
    if user.has_local_password:
        return True
    return CountLocalFactors(SqlLocalFactorDirectory(db)).for_user(user.id).passkeys > 0


@router.post("/token", response_model=SsoSessionResponse)
def exchange_ticket(
    body: SsoTicketRequest,
    response: Response,
    db: DbDep,
    use_case: Annotated[ExchangeSsoTicket, Depends(dependencies.exchange_sso_ticket)],
) -> SsoSessionResponse:
    """Exchange the redemption ticket for tokens (single use)."""
    session = use_case.execute(ticket=body.ticket)
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )
    established = establish_session(response, user, SessionCarryOver(federated_login=session.login))
    logger.info("sso_login_succeeded")
    return SsoSessionResponse(expires_in=established.expires_in, redirect_to=session.redirect_to)


# The notice body is a single ``application/x-www-form-urlencoded`` field. **Don't use
# ``Form()``** — FastAPI's ``Form`` requires ``python-multipart``, which would add a template
# dependency for this one place.
#: Upper limit on the body accepted. Only one ``logout_token`` fits, so this is plenty.
_LOGOUT_BODY_MAX_BYTES = 16 * 1024


@router.post("/backchannel-logout", include_in_schema=False)
async def receive_backchannel_logout(
    request: Request,
    receiver: Annotated[dependencies.BackchannelLogout, Depends(dependencies.receive_backchannel_logout)],
) -> StatusResponse:
    """Receive logout notices from the IdP (OpenID Connect Back-Channel Logout 1.0. ADR-0077 §3).

    ⚠ **This endpoint can be hit unauthenticated.** The only proof of the sender is the
    ``logout_token`` signature, so anything failing validation is dropped with 400 and no reason
    (don't reveal how far it got).

    ⚠ **No cookie needed.** The CSRF check only applies to "cookie-authenticated state changes",
    so this cookie-less call is out of scope (``CsrfMiddleware``).

    ⚠ **The response only means "received".** The session actually ends the next time that
    token is presented (the server keeps no copy of sessions).

    Validation makes synchronous HTTP calls for discovery and JWKS, so the work is offloaded to
    the thread pool (same reason ``/login`` and ``/callback`` are ``def``).
    """
    logout_token = _logout_token_of(await _bounded_body(request))
    # The connection (= tenant) is determined by the notice's issuer. The signature is checked
    # with that connection's keys
    use_case = receiver.from_issuer(_unverified_issuer_of(logout_token))
    notice = await run_in_threadpool(use_case.execute, logout_token=logout_token)
    logger.info(
        "sso_backchannel_logout_received: scope=%s",
        "session" if notice.session.session_id else "subject",
    )
    return StatusResponse(status="ok")


async def _bounded_body(request: Request) -> bytes:
    """Read the body. **Refuse oversized bodies unread** (the endpoint is unauthenticated)."""
    declared = request.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > _LOGOUT_BODY_MAX_BYTES:
        raise InvalidLogoutTokenError
    body = await request.body()
    if len(body) > _LOGOUT_BODY_MAX_BYTES:
        raise InvalidLogoutTokenError
    return body


def _logout_token_of(body: bytes) -> str:
    """Extract ``logout_token=<JWT>``. Reject if missing, empty, or repeated."""
    values = [value for name, value in parse_qsl(body.decode("ascii", "replace")) if name == "logout_token"]
    if len(values) != 1 or not values[0]:
        raise InvalidLogoutTokenError
    return values[0]


def _unverified_issuer_of(token: str) -> str:
    """``iss`` used to decide which connection's keys to verify with, before the signature check.

    ⚠ **Don't trust the value read here.** An unregistered issuer has no connection and fails
    validation. Claiming a registered issuer only passes with that issuer's signature.
    """
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as error:
        raise InvalidLogoutTokenError from error
    issuer = claims.get("iss")
    return issuer if isinstance(issuer, str) else ""


def _login_screen_of(tenant: Tenant | None) -> str:
    """Tenant entrance (``/t/<slug>/login``). The shared entrance if the tenant is unknown."""
    return f"/t/{tenant.slug}/login" if tenant is not None else LOGIN_SCREEN


def _redirect(url: str) -> RedirectResponse:
    """Send back to the SPA. Drop the round-trip cookie here (the round trip is over)."""
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    transaction_cookie.clear(response, path=router.prefix)
    return response


def _to_login_screen(code: str, screen: str = LOGIN_SCREEN) -> RedirectResponse:
    safe = code if _ERROR_CODE.fullmatch(code) else _GENERIC_ERROR
    return _redirect(f"{screen}?sso_error={safe}")


def _silently_declined(transaction: LoginTransaction, screen: str) -> RedirectResponse:
    """Tried silently, but the user wasn't signed in at the IdP (ADR-0077 §9).

    **Not recorded as a failure.** It would pile up audit entries for people who merely opened
    the login screen.
    The destination (``redirect_to``) is carried back so signing in via the button returns there too.
    """
    logger.info("sso_silent_login_declined")
    query = urlencode({SILENT_DECLINED_PARAM: "declined", "redirect_to": transaction.redirect_to})
    return _redirect(f"{screen}?{query}")


def _link_failed(code: str) -> RedirectResponse:
    """Return a link failure to the settings screen.

    **Not written to the audit log.** No binding was added, so "who did what" hasn't changed;
    tracking down the cause is the app log's job (ADR-0075 §1).
    """
    safe = code if _ERROR_CODE.fullmatch(code) else _GENERIC_ERROR
    return _redirect(f"{SECURITY_SCREEN}?sso_link_error={safe}")


def _failed(audit: AuditRecorderDep, reason: str, screen: str = LOGIN_SCREEN) -> RedirectResponse:
    """Record the failure and return to the login screen.

    No actor is recorded: before the SSO login succeeds, "who tried" is not known
    (ADR-0075 §1).
    """
    safe = reason if _ERROR_CODE.fullmatch(reason) else _GENERIC_ERROR
    audit.execute(AuditEventType.SSO_LOGIN_FAILED, AuditResult.FAILURE, reason=safe)
    logger.warning("sso_login_failed: %s", safe)
    return _to_login_screen(safe, screen)


def _record_success(audit: AuditRecorderDep, account: ResolvedAccountDto) -> None:
    _record_account_changes(audit, account)
    audit.as_actor(account.user_id).execute(AuditEventType.SSO_LOGIN_SUCCEEDED, reason="method=sso")


def _record_account_changes(audit: AuditRecorderDep, account: ResolvedAccountDto) -> None:
    """Record that a user was created / bound.

    The renewal round trip (ADR-0104) doesn't record the success itself: it would pile up every
    5 minutes and bury real logins.
    """
    recorder = audit.as_actor(account.user_id)
    if account.provisioned:
        recorder.execute(AuditEventType.SSO_USER_PROVISIONED)
    elif account.linked:
        recorder.execute(AuditEventType.SSO_IDENTITY_LINKED)


__all__ = ["HANDOFF_SCREEN", "LOGIN_SCREEN", "SILENT_DECLINED_PARAM", "router"]
