"""SSO（OpenID Connect）ログイン API。

経路は 10。

- ``GET /provider`` — ログイン画面が「SSO で入る」ボタンを出すかを問い合わせる
- ``GET /login`` — IdP の認可エンドポイントへブラウザを送り出す
- ``GET /callback`` — IdP からの戻り。引き換え券を付けて SPA へ戻す
- ``POST /token`` — 引き換え券をトークンへ換える（Cookie もここで載せる）
- ``GET /logout`` — サインアウトを IdP まで通す（**既定では無効**）
- ``GET /signed-out`` — その戻り。ログイン画面へ返すだけ
- ``POST /backchannel-logout`` — IdP からの停止の通知を受ける（ADR-0036）
- ``GET /link`` — 自分の連携の状態を答える（設定画面。ADR-0040）
- ``POST /link/start`` — 連携の往復を始める（入っている本人が押す）
- ``DELETE /link`` — 連携を外す

``/callback`` は**ログインの戻りと連携の戻りを兼ねる**。どちらの後始末をするかは
往復状態の ``purpose`` で決める ——IdP に登録する戻り先の URI を 1 つに保つため
（ADR-0040）。⚠ **目的をクエリで渡さない。** URL を書き換えるだけで化けさせられる。

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
from urllib.parse import parse_qsl, quote

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
    ResolvedAccountDto,
)
from bounded_contexts.identity_federation.application.use_cases.build_rp_logout_url import (
    BuildRpLogoutUrl,
)
from bounded_contexts.identity_federation.application.use_cases.complete_sso_link import (
    CompleteSsoLink,
)
from bounded_contexts.identity_federation.application.use_cases.complete_sso_login import (
    CompleteSsoLogin,
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
from bounded_contexts.identity_federation.application.use_cases.receive_backchannel_logout import (
    ReceiveBackchannelLogout,
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
    SsoNotConfiguredError,
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
from bounded_contexts.identity_federation.presentation import dependencies, transaction_cookie
from bounded_contexts.identity_federation.presentation.schemas import (
    FederatedLinkResponse,
    SsoLinkStartResponse,
    SsoProviderResponse,
    SsoSessionResponse,
    SsoTicketRequest,
)
from presentation.fastapi.dependencies.auth import (
    get_current_user,
    get_current_user_or_none,
)
from presentation.fastapi.schemas.auth import StatusResponse
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
#: 連携の戻りの着地点（設定画面のセキュリティ区画。ADR-0040）
SECURITY_SCREEN = "/profile/security"

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


class _CallbackTools:
    """戻りの後始末に要る道具。

    ログインの戻りと連携の戻りを 1 つの経路で受けるので、両方の道具をここへまとめる
    （ハンドラの引数を増やさないため。``SsoCallbackQuery`` と同じ書き方）。
    """

    def __init__(
        self,
        login: Annotated[CompleteSsoLogin, Depends(dependencies.complete_sso_login)],
        link: Annotated[CompleteSsoLink, Depends(dependencies.complete_sso_link)],
        audit: AuditRecorderDep,
        viewer: Annotated[User | None, Depends(get_current_user_or_none)] = None,
    ) -> None:
        self.login = login
        self.link = link
        self.audit = audit
        self.viewer = viewer


@router.get("/callback", include_in_schema=False)
def complete_callback(
    query: Annotated[SsoCallbackQuery, Depends()],
    tools: Annotated[_CallbackTools, Depends()],
    tx: Annotated[str | None, Cookie(alias=transaction_cookie.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """IdP からの戻りを受け取る。ログインの戻りと連携の戻りを兼ねる（ADR-0040）。

    往復状態の Cookie は、成功しても失敗しても落とす（1 回の往復で使い切る）。

    ⚠ **Cookie が復元できないときはログインの戻りとして扱う。** 連携だったのか
    どうかは、その往復状態にしか書かれていないためである（結果は
    ``sso_state_invalid`` でログイン画面へ戻る。やり直せば連携は通る）。
    """
    transaction = transaction_cookie.read(tx)
    if transaction is not None and transaction.purpose is TransactionPurpose.LINK:
        return _complete_link(query, tools, transaction)
    return _complete_login(query, tools, transaction)


def _complete_login(
    query: SsoCallbackQuery,
    tools: _CallbackTools,
    transaction: LoginTransaction | None,
) -> RedirectResponse:
    """引き換え券を付けて SPA へ戻す。"""
    if query.error is not None or not query.code or not query.state:
        return _failed(tools.audit, query.error or "sso_callback_invalid")
    try:
        handoff = tools.login.execute(code=query.code, state=query.state, transaction=transaction)
    except IdentityFederationError as error:
        return _failed(tools.audit, error.code)
    _record_success(tools.audit, handoff.account)
    return _redirect(f"{HANDOFF_SCREEN}?ticket={quote(handoff.ticket)}")


def _complete_link(
    query: SsoCallbackQuery,
    tools: _CallbackTools,
    transaction: LoginTransaction,
) -> RedirectResponse:
    """戻ってきた相手を、往復を始めた利用者へ結び付けて設定画面へ返す。

    ⚠ **いま入っている利用者を見て決め直さない。** 誰に結び付けるかは往復を始めた
    時点で決まっている（往復状態の ``user_id``）。ここで見るのは「その本人が
    まだ入っているか」だけで、入れ替わっていれば断る。
    """
    viewer = tools.viewer
    if viewer is None:
        return _link_failed(SsoLinkSessionMismatchError.code)
    if query.error is not None or not query.code or not query.state:
        return _link_failed(query.error or "sso_callback_invalid")
    callback = SsoCallback(code=query.code, state=query.state, transaction=transaction)
    try:
        tools.link.execute(callback=callback, user_id=viewer.id)
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
    """連携の往復を始める。**画面はこの URL へ自分で遷移する。**

    303 を返さず XHR にしているのは、⚠ **認証が切れている相手に 401 を返せる**
    ようにするため。画面遷移で始めると、切れていた場合に JSON の生文字列が
    見えるだけで、やり直す導線が出せない。

    ⚠ **CSRF の守りはここで効く。** Cookie で認証する更新系なので
    ``CsrfMiddleware`` の対象になり、よその頁からは起こせない。
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
    """自分の連携の状態を答える（ADR-0040）。他人の分は見えない。"""
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
    """連携を外す。⚠ **外すと入れなくなる利用者は断る**（ADR-0040）。"""
    provider = dependencies.identity_provider()
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
    """IdP を外したあとも、この利用者に**入り口**が残るか。

    ⚠ **二要素認証は入り口ではない。** パスワードの後ろに置く second factor なので、
    それだけでは入れない。数えるのはパスワードとパスキーである。
    """
    if user.has_local_password:
        return True
    return CountLocalFactors(SqlLocalFactorDirectory(db)).for_user(user.id).passkeys > 0


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
    established = establish_session(response, user, federated_login=session.login)
    logger.info("sso_login_succeeded")
    return SsoSessionResponse(expires_in=established.expires_in, redirect_to=session.redirect_to)


# 通知の本体は ``application/x-www-form-urlencoded`` の 1 フィールドだけ。**``Form()`` を
# 使わない**——FastAPI の ``Form`` は ``python-multipart`` を要求するので、この 1 か所の
# ために雛形の依存を 1 つ増やすことになる。
#: 受け取る本文の上限。``logout_token`` 1 本しか入らないので、これで充分に広い。
_LOGOUT_BODY_MAX_BYTES = 16 * 1024


@router.post("/backchannel-logout", include_in_schema=False)
async def receive_backchannel_logout(
    request: Request,
    use_case: Annotated[ReceiveBackchannelLogout, Depends(dependencies.receive_backchannel_logout)],
) -> StatusResponse:
    """IdP からの停止の通知を受ける（OpenID Connect Back-Channel Logout 1.0。ADR-0036）。

    ⚠ **この口は未認証で叩ける。** 相手の証明は ``logout_token`` の署名だけなので、
    検証を通らないものは理由を返さずに 400 で落とす（どこまで通ったかを教えない）。

    ⚠ **Cookie は要らない。** CSRF の検査は「Cookie で認証している更新系」にだけ
    掛かるので、Cookie を持たないこの呼び出しは対象外になる（``CsrfMiddleware``）。

    ⚠ **応答は「受け取った」だけを意味する。** 実際にセッションが終わるのは、次に
    そのトークンが提示されたときである（サーバーにセッションの控えが無いため）。

    検証では discovery と JWKS の同期 HTTP が出るので、処理はスレッドプールへ逃がす
    （``/login`` や ``/callback`` を ``def`` にしているのと同じ理由）。
    """
    logout_token = _logout_token_of(await _bounded_body(request))
    notice = await run_in_threadpool(use_case.execute, logout_token=logout_token)
    logger.info(
        "sso_backchannel_logout_received: scope=%s",
        "session" if notice.session.session_id else "subject",
    )
    return StatusResponse(status="ok")


async def _bounded_body(request: Request) -> bytes:
    """本文を読む。**大きすぎるものは読まずに断る**（未認証で叩ける口のため）。"""
    declared = request.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > _LOGOUT_BODY_MAX_BYTES:
        raise InvalidLogoutTokenError
    body = await request.body()
    if len(body) > _LOGOUT_BODY_MAX_BYTES:
        raise InvalidLogoutTokenError
    return body


def _logout_token_of(body: bytes) -> str:
    """``logout_token=<JWT>`` を取り出す。無い・空・複数あるものは受け取らない。"""
    values = [value for name, value in parse_qsl(body.decode("ascii", "replace")) if name == "logout_token"]
    if len(values) != 1 or not values[0]:
        raise InvalidLogoutTokenError
    return values[0]


def _redirect(url: str) -> RedirectResponse:
    """SPA へ戻す。往復状態の Cookie はここで落とす（往復が終わったため）。"""
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    transaction_cookie.clear(response, path=router.prefix)
    return response


def _to_login_screen(code: str) -> RedirectResponse:
    safe = code if _ERROR_CODE.fullmatch(code) else _GENERIC_ERROR
    return _redirect(f"{LOGIN_SCREEN}?sso_error={safe}")


def _link_failed(code: str) -> RedirectResponse:
    """連携の失敗を設定画面へ返す。

    **監査ログには残さない。** 結び付きは増えていないので「誰が何をしたか」は
    変わっておらず、原因を追うのはアプリログの仕事になる（ADR-0013）。
    """
    safe = code if _ERROR_CODE.fullmatch(code) else _GENERIC_ERROR
    return _redirect(f"{SECURITY_SCREEN}?sso_link_error={safe}")


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
