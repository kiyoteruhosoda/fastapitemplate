"""SSO（OpenID Connect）ログイン API。

経路は 6 つ。

- ``GET /provider`` — ログイン画面が「SSO で入る」ボタンを出すかを問い合わせる
- ``GET /login`` — IdP の認可エンドポイントへブラウザを送り出す
- ``GET /callback`` — IdP からの戻り。引き換え券を付けて SPA へ戻す
- ``POST /token`` — 引き換え券をトークンへ換える（Cookie もここで載せる）
- ``GET /logout`` — サインアウトを IdP まで通す（**既定では無効**）
- ``GET /signed-out`` — その戻り。ログイン画面へ返すだけ

``/login`` は**往復状態（``state`` / ``nonce`` / ``code_verifier``）を署名付き Cookie に
入れてから**送り出し、``/callback`` はそれを復元して照合する（ADR-0025）。サーバー側に
控えを持たないので、``state`` を知っているだけの相手は戻りを完了できない ——攻撃者が
始めた認可要求を踏まされても、被害者のブラウザには対応する Cookie が無い（ログイン CSRF）。

``/login`` と ``/callback`` は**ブラウザの画面遷移**で、応答本文を SPA は読めない。
そのため失敗も JSON ではなくログイン画面への転送で返す（``?sso_error=<code>``）。
表示文言はフロントエンドが決める（CLAUDE.md「国際化」）。

トークンを URL に載せないための引き換え券は ADR-0025。
"""

from __future__ import annotations

import logging
import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from bounded_contexts.identity_federation.application.dto.sso_dto import (
    ResolvedAccountDto,
)
from bounded_contexts.identity_federation.application.use_cases.build_rp_logout_url import (
    BuildRpLogoutUrl,
)
from bounded_contexts.identity_federation.application.use_cases.complete_sso_login import (
    CompleteSsoLogin,
)
from bounded_contexts.identity_federation.application.use_cases.describe_sso_provider import (
    DescribeSsoProvider,
)
from bounded_contexts.identity_federation.application.use_cases.exchange_sso_ticket import (
    ExchangeSsoTicket,
)
from bounded_contexts.identity_federation.application.use_cases.start_sso_login import (
    StartSsoLogin,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityFederationError,
)
from bounded_contexts.identity_federation.presentation import dependencies, transaction_cookie
from bounded_contexts.identity_federation.presentation.schemas import (
    SsoProviderResponse,
    SsoSessionResponse,
    SsoTicketRequest,
)
from presentation.fastapi.services.session_cookies import establish_session
from shared.infrastructure.models import User
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]

# 戻り先の SPA の経路（フロントエンドのルーティングと対で合わせる）
LOGIN_SCREEN = "/login"
HANDOFF_SCREEN = "/login/sso"

# IdP が返すエラーコードはそのまま画面の URL へ載るため、素性の分かる形だけを通す
# （反射した文字列でリンクを組み立てられないようにする）。照合は ``fullmatch``——
# ``$`` は末尾の改行の直前にも当たるため、``match`` だと改行を通してしまう。
_ERROR_CODE = re.compile(r"[a-z_]{1,64}")
_GENERIC_ERROR = "sso_error"


class SsoCallbackQuery:
    """IdP からの戻りに付くクエリ（成功なら ``code`` と ``state``）。"""

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
async def describe_provider(
    use_case: Annotated[DescribeSsoProvider, Depends(dependencies.describe_sso_provider)],
) -> SsoProviderResponse:
    """SSO が使えるかを答える（未認証で呼べる。接続先の情報は返さない）。"""
    provider = use_case.execute()
    return SsoProviderResponse(
        enabled=provider.enabled,
        display_name=provider.display_name,
        local_login_enabled=settings.local_login_enabled,
        rp_logout_enabled=provider.rp_logout_enabled,
    )


# ``/logout`` は IdP へ discovery を出すことがあるので ``def``（``/login`` と同じ理由）。
@router.get("/logout", include_in_schema=False)
def logout(
    use_case: Annotated[BuildRpLogoutUrl, Depends(dependencies.build_rp_logout_url)],
    sec_fetch_site: Annotated[str | None, Header(alias="Sec-Fetch-Site")] = None,
) -> RedirectResponse:
    """サインアウトを IdP まで通す。**アプリのセッションはここでは触らない。**

    終わらせるのは ``POST /api/auth/logout`` の仕事で、画面はそれを済ませてから
    ここへ遷移する。二重に持たせない——片方だけ直したときにずれるため。

    **通せないときはログイン画面へ返すだけ**（設定が無効・SSO が使えない・IdP が
    ``end_session_endpoint`` を出していない・よそから呼ばれた）。ここで失敗を
    見せても、利用者にできることが無い。
    """
    if not _from_this_site(sec_fetch_site):
        logger.warning("sso_logout_rejected_cross_site")
        return _redirect(LOGIN_SCREEN)
    return _redirect(use_case.execute() or LOGIN_SCREEN)


def _from_this_site(sec_fetch_site: str | None) -> bool:
    """この経路への遷移が**自分のサイトから**始まったかを見る。

    ⚠ **この口は未認証で状態を変える。** しかも変えるのは**IdP の SSO セッション**で、
    それは同じ IdP を使う全アプリで共有されている。守らないと、よその頁が
    ``<img src="…/api/auth/sso/logout">`` を置くだけで**利用者を他アプリからも
    締め出せる**（被害はログインし直しまでだが、頼んでいない副作用ではある）。

    ⚠ **IdP の確認画面はあてにしない。** OIDC は ``id_token_hint`` が無いとき OP が
    確認を挟むことを *SHOULD* としているだけで、**自前 idp (assay) は挟まない**
    （2026-09-07 に実装を確認）。歯止めはここしか無い。

    Cookie ではなくブラウザが付ける ``Sec-Fetch-Site`` を見る。CSRF トークンを使わない
    のは、ここが**画面遷移**だから——トークンを載せるには JavaScript で URL を組む
    ことになり、``<a href>`` で開けるという性質を捨てることになる。

    通すのは自分のオリジンからの遷移 (``same-origin``) と、利用者が自分で叩いた場合
    (``none``。アドレス欄・ブックマーク)。**ヘッダーごと無い場合も通す**——付けない
    のは古いブラウザで、そこを閉じるとサインアウトできなくなる。よその頁から
    起こした遷移では**ブラウザが必ず付ける**ので、塞ぎたい経路は塞がる。
    """
    return sec_fetch_site is None or sec_fetch_site in {"same-origin", "none"}


@router.get("/signed-out", include_in_schema=False)
def signed_out() -> RedirectResponse:
    """IdP でサインアウトを終えた足の着地点。

    **この URI を IdP のクライアントに登録しておく**（``post_logout_redirect_uri``）。
    未登録でも壊れはせず、IdP 自身の完了ページで止まる。

    ここが独立した経路なのは、**登録する文字列を SPA のルーティングから切り離す**
    ため。画面の経路を変えるたびに IdP 側の登録を直すことになると、片方だけ直して
    黙って外れる。
    """
    return _redirect(f"{LOGIN_SCREEN}?signed_out=1")


# ``/login`` と ``/callback`` は IdP へ同期の HTTP を出す（discovery・トークン交換）。
# ``async def`` にするとその往復のあいだイベントループが止まり、同じワーカーの
# 全リクエストが待たされる。``def`` で定義してスレッドプールへ逃がす。
@router.get("/login", include_in_schema=False)
def start_login(
    use_case: Annotated[StartSsoLogin, Depends(dependencies.start_sso_login)],
    redirect_to: Annotated[str | None, Query(max_length=255)] = None,
) -> RedirectResponse:
    """IdP へ送り出す。設定が無い・IdP と話せない場合はログイン画面へ戻す。"""
    try:
        authorization = use_case.execute(redirect_to=redirect_to)
    except IdentityFederationError as error:
        logger.warning("sso_start_failed: %s", error.code)
        return _to_login_screen(error.code)
    response = RedirectResponse(url=authorization.authorization_url, status_code=status.HTTP_303_SEE_OTHER)
    transaction_cookie.issue(response, authorization.transaction, path=router.prefix)
    return response


@router.get("/callback", include_in_schema=False)
def complete_login(
    query: Annotated[SsoCallbackQuery, Depends()],
    use_case: Annotated[CompleteSsoLogin, Depends(dependencies.complete_sso_login)],
    audit: AuditRecorderDep,
    tx: Annotated[str | None, Cookie(alias=transaction_cookie.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """IdP からの戻りを受け取り、引き換え券を付けて SPA へ戻す。

    往復状態の Cookie は、成功しても失敗しても落とす（1 回の往復で使い切る）。
    """
    if query.error is not None or not query.code or not query.state:
        return _failed(audit, query.error or "sso_callback_invalid")
    try:
        handoff = use_case.execute(
            code=query.code,
            state=query.state,
            transaction=transaction_cookie.read(tx),
        )
    except IdentityFederationError as error:
        return _failed(audit, error.code)
    _record_success(audit, handoff.account)
    return _redirect(f"{HANDOFF_SCREEN}?ticket={quote(handoff.ticket)}")


@router.post("/token", response_model=SsoSessionResponse)
async def exchange_ticket(
    body: SsoTicketRequest,
    response: Response,
    db: DbDep,
    use_case: Annotated[ExchangeSsoTicket, Depends(dependencies.exchange_sso_ticket)],
) -> SsoSessionResponse:
    """引き換え券をトークンへ換える（1 回限り）。"""
    session = use_case.execute(ticket=body.ticket)
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )
    established = establish_session(response, user)
    logger.info("sso_login_succeeded")
    return SsoSessionResponse(expires_in=established.expires_in, redirect_to=session.redirect_to)


def _redirect(url: str) -> RedirectResponse:
    """SPA へ戻す。往復状態の Cookie はここで落とす（往復が終わったため）。"""
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    transaction_cookie.clear(response, path=router.prefix)
    return response


def _to_login_screen(code: str) -> RedirectResponse:
    safe = code if _ERROR_CODE.fullmatch(code) else _GENERIC_ERROR
    return _redirect(f"{LOGIN_SCREEN}?sso_error={safe}")


def _failed(audit: AuditRecorderDep, reason: str) -> RedirectResponse:
    """失敗を記録してログイン画面へ戻す。

    実行者は入れない。SSO のログインが通っていない時点では「誰が試したか」が
    分かっていないため（ADR-0013）。
    """
    safe = reason if _ERROR_CODE.fullmatch(reason) else _GENERIC_ERROR
    audit.execute(AuditEventType.SSO_LOGIN_FAILED, AuditResult.FAILURE, reason=safe)
    logger.warning("sso_login_failed: %s", safe)
    return _to_login_screen(safe)


def _record_success(audit: AuditRecorderDep, account: ResolvedAccountDto) -> None:
    recorder = audit.as_actor(account.user_id)
    if account.provisioned:
        recorder.execute(AuditEventType.SSO_USER_PROVISIONED)
    elif account.linked:
        recorder.execute(AuditEventType.SSO_IDENTITY_LINKED)
    recorder.execute(AuditEventType.SSO_LOGIN_SUCCEEDED, reason="method=sso")


__all__ = ["HANDOFF_SCREEN", "LOGIN_SCREEN", "router"]
