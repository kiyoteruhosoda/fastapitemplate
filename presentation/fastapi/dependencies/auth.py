"""FastAPI JWT 認証依存コンポーネント。

``Depends()`` ベースで JWT を検証し、検証済みの ``AuthenticatedPrincipal`` を
ルーターへ渡す。認可は :func:`require_permission`（scope ベース）で宣言する。
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

# アクセストークンを格納する Cookie 名（ログイン時に auth ルーターが設定する）
ACCESS_TOKEN_COOKIE = "access_token"
# リフレッシュトークンの Cookie。**経路を更新の口だけに絞る**——他のリクエストに
# 付いて回ると、長命な資格情報が送られる回数がむやみに増える（ADR-0076 §4）。
REFRESH_TOKEN_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth/refresh"
# ログインを終わらせるためだけの札（ADR-0091）。更新の Cookie は経路を絞ってあってログアウトの口へ
# 届かず、アクセストークンの Cookie は寿命で消える。札ができるのはそのログインを終わらせることだけ。
LOGOUT_TOKEN_COOKIE = "logout_token"
LOGOUT_COOKIE_PATH = "/api/auth/logout"


def set_access_token_cookie(response: Response, token: str) -> None:
    """アクセストークンを Cookie へ載せる。

    トークンを発行する経路（パスワード・リフレッシュ・パスキー）が複数あるため、
    属性の付け方をここ 1 か所に集約する。
    """
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        max_age=settings.access_token_expires_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


def set_refresh_token_cookie(response: Response, token: str) -> None:
    """リフレッシュトークンを Cookie へ載せる（ADR-0076 §4）。

    ⚠ **応答本文には載せない。** Cookie は自動で送られるので、本文にも返すと
    XSS が ``POST /api/auth/refresh`` を叩いて新しいトークンを読めてしまい、
    ``httpOnly`` が意味を持たなくなる。
    """
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        token,
        max_age=settings.refresh_token_expires_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def set_logout_token_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        LOGOUT_TOKEN_COOKIE,
        token,
        max_age=settings.refresh_token_expires_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=LOGOUT_COOKIE_PATH,
    )


def clear_access_token_cookie(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(LOGOUT_TOKEN_COOKIE, path=LOGOUT_COOKIE_PATH)


# Authorization ヘッダー優先、無ければ Cookie フォールバック
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
    """JWT を検証して ``AuthenticatedPrincipal`` を返す。失敗時は 401。**機械の主体も通す**（ADR-0087）。

    ⚠ **これを直に使うのは、scope で守る関門だけ**（:func:`require_permission` /
    :func:`require_any_permission` と、主体のテナントを取り出す依存関数）。機械に出したトークンは
    scope が許可簿の操作に絞られているので、scope で守られた口なら通してよい。
    それ以外の口は :func:`get_current_principal`（人だけ）を使う。

    ⚠ **DB を引かない**（ADR-0076 §5）。認可の材料はすべてトークンのクレームに
    載っている。利用者の行そのものが要る経路は :func:`get_current_user` を使う
    ——そちらは 1 件引くが、**認可の判定ではない**。
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
        logger.debug("JWT 認証失敗: %s", reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "reason": reason},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 以降のログへ user.id_hash を伝播する（PII は残さない）
    user_id_hash_var.set(principal.id_hash)
    # 監査ログの「誰が」。呼び出し側が主体を引き回さなくても記録できるようにする
    actor_user_id_var.set(principal.user_id)
    return principal


MACHINE_NOT_ALLOWED = "machine_not_allowed"
TWO_FACTOR_SETUP_REQUIRED = "two_factor_setup_required"
#: 二要素の登録待ちのログインで通る口（ADR-0093）。更新とログアウトは主体を見ないので、ここに無くても通る。
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
    """人の主体を返す。**機械の主体は 403**（ADR-0087 決定 4）。

    scope で守られていない口（本人の設定・ロールの切り替え・資格情報の作り替えなど）は、
    許可簿の操作で絞れない。機械に開けると、振る舞う利用者として何でもできてしまう ——
    既定で断り、開けるのは scope で守った口だけにする。
    """
    if principal.is_machine:
        refuse_machine(principal, _operation_of(request))
    if (request.method, request.url.path) not in _OPEN_DURING_TWO_FACTOR_SETUP:
        refuse_during_two_factor_setup(principal)
    return principal


def refuse_during_two_factor_setup(principal: AuthenticatedPrincipal) -> None:
    """二要素の登録待ちのログインを断る（ADR-0093）。画面はこの 403 で登録の画面へ切り替わる。"""
    if principal.two_factor_setup_required:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": TWO_FACTOR_SETUP_REQUIRED})


def refuse_machine(principal: AuthenticatedPrincipal, operation: str) -> NoReturn:
    """機械の主体を断る（人だけの口）。監査に残してから 403。"""
    _refuse_machine(principal, operation, "person_only")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": MACHINE_NOT_ALLOWED})


def _operation_of(request: Request) -> str:
    """監査に残す操作の名前（``GET /api/items`` のような経路の型。値の入った URL は残さない）。"""
    route = request.scope.get("route")
    path = route.path if isinstance(route, Route) else request.url.path
    return f"{request.method} {path}"


def _record_machine_write(principal: AuthenticatedPrincipal, request: Request) -> None:
    """機械が書く操作を監査に残す（どの機械が・誰として・何を。ADR-0087）。読むだけの操作は残さない。"""
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
    """機械の操作を断ったことを監査に残す（ADR-0087 決定 5。``client_id``・操作・理由）。"""
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
    """scope が足りない機械の操作を監査に残す。理由は「許可簿に無い」か「利用者のロールに無い」。"""
    from bounded_contexts.identity_federation.domain.value_objects.machine_client import (
        find_machine_client,
        parse_machine_clients,
    )

    client = find_machine_client(parse_machine_clients(settings.machine_clients), principal.machine_client_id or "")
    missing = [code for code in codes if not principal.can(code)]
    outside = [code for code in missing if client is None or not client.allows(code)]
    why = "not_in_allowlist" if outside else "role_lacks_permission"
    _refuse_machine(principal, ",".join(missing), why)


async def get_current_user(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> User:
    """認証済み主体に対応する ``User`` 行を返す。

    ロールの一覧のように「トークンに載っていない現在の状態」が要るときだけ使う
    （認可の判定は :func:`require_permission` の scope で行う）。
    """
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    return user


async def get_current_user_or_none(
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: Session = Depends(get_db),
) -> User | None:
    """入っていれば利用者を、入っていなければ ``None`` を返す（401 にしない）。

    ⚠ **これを認可に使わない。** 用があるのは**ブラウザの画面遷移**で戻ってくる
    経路だけである（ADR-0077 §5 の連携の戻り）。そこで 401 を返すと、利用者には
    JSON の生文字列が見えるだけで、やり直す導線も出せない。認可が要る口は
    :func:`get_current_principal` 系を使う。
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
    """いま操作している利用者と、その入り口（ADR-0077 §3）。

    ``federated_login`` が ``None`` ならローカルのログイン。新しいトークンを
    出し直す口（ロールの切り替え）は、**これをそのまま引き継ぐ**。
    """

    user: User
    federated_login: FederatedLogin | None
    #: いまのアクティブロール（ADR-0078 §1）。出し直すときに引き継ぐ。
    active_role: str | None = None
    #: 本人が最後に実際にサインインした時刻（ADR-0076 §10）。出し直すときに引き継ぐ。
    authenticated_at: datetime | None = None
    #: このログインの控え（ADR-0091）。ロールの切り替えで引き継ぐ。
    refresh_session_id: str | None = None
    #: パスキーで入ったログインか（ADR-0093）。出し直すときに引き継ぐ。
    signed_in_with_passkey: bool = False


async def get_current_session(
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: Session = Depends(get_db),
) -> CurrentSession:
    """認証済みの利用者と、そのセッションがどこから始まったかを返す。

    トークンは :func:`get_current_principal` が既に検証している（同じリクエストの
    同じ値）。ここで読むのは宛名のクレームだけで、認証をやり直しているのではない。

    ⚠ **ここは「新しいトークンを出す」経路のためにある**（ロールの切り替え）。
    アクセストークンの検証が DB を引かなくなったので（ADR-0076 §5）、**出し直しの
    経路だけは止まっていないことを確かめる** ——確かめないと、止められた利用者が
    切り替えを繰り返すだけで**いつまでも新しいトークンを受け取れる**。
    **寿命による上限が、そこで破れる。**
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


async def get_settled_principal(
    # ⚠ **値は使わない。関門として通すためだけに置いてある**（名前の ``_`` はその印）。
    _session: CurrentSession = Depends(get_current_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
) -> AuthenticatedPrincipal:
    """**資格情報を作り替える経路**のための関門（ADR-0076 §5 決定 6）。

    二要素認証やパスキーの登録・解除は「新しい入り口を作る」操作である。
    ⚠ **アクセストークンの検証が DB を引かなくなったので、止められた利用者でも
    手元の 1 枚は寿命まで通る。** その 1 枚で新しい入り口を作られては、止めた意味が
    半分無くなる ——ここだけは、いまの状態を確かめてから通す。

    確かめているのは :func:`get_current_session` である（利用者が生きていること、
    IdP 側で止められていないこと）。**出し直しの経路と同じ関門**を使う。
    """
    from presentation.fastapi.services.token_service import TokenService

    token = _extract_token(credentials, access_token_cookie)
    principal, _ = TokenService.verify_access_token_with_reason(token or "")
    if principal is None:  # pragma: no cover - 関門を通った時点で必ず読める
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )
    return principal


REAUTHENTICATION_REQUIRED = "reauthentication_required"


def ensure_recent_sign_in(principal: AuthenticatedPrincipal) -> None:
    """**入り口そのものを作り替える操作**の前に、入り直したばかりかを確かめる（ADR-0076 §10）。

    盗まれたセッションでパスキーを足す・メールを替えると、そのあとはパスワードも
    二要素も無しに入り続けられる。「最後に実際にサインインしてから
    ``RECENT_SIGN_IN_SECONDS`` 以内」でなければ 403 で断り、画面は入り直しへ送る。
    パスワードを持たない（SSO だけの）利用者にも同じように効く。
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
    """:func:`ensure_recent_sign_in` を関門として掛ける依存関数。"""
    ensure_recent_sign_in(principal)
    return principal


def require_permission(*codes: str) -> Callable[..., Awaitable[AuthenticatedPrincipal]]:
    """指定された権限を全て保持している場合のみアクセスを許可する依存関数ファクトリ。

    使用例::

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
    """指定された権限を **いずれか 1 つでも** 保持していればアクセスを許可する。

    ある資源を読む理由が複数の職掌にまたがるとき（ロールの一覧は「ロールを管理
    する」ためにも「ユーザーへロールを割り当てる」ためにも要る。ADR-0078 §2）に使う。
    **書き込みには使わない** — 権限を足す側は 1 つの scope で明示する。
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
