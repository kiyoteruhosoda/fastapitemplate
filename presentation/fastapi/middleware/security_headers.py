"""全部の応答に守りのヘッダを付ける（ADR-0073 §5）。

前段の nginx に書くと、派生のアプリごとに deploy-repo の写しへ書き写すことになり、
写し忘れる（2026-10-21 の確認で、試し場の写しは雛形の ``/metrics`` の閉じ方すら
写していなかった）。アプリ自身が付ければ、雛形から起こしたアプリには必ず入る。

- **CSP** は ``default-src 'self'``。画面はインラインのスクリプトも外部の資源も
  使っていない。例外は 2 つだけ: 二要素の QR コードを ``data:`` の画像で出すので
  ``img-src`` に ``data:``、枠に埋め込ませないので ``frame-ancestors 'none'``。
- **``frame-src``** は自分のオリジンと、IdP の発行者と同じ親ドメインの名前（``https://*.<親>``）。
  切れたログインを見えない枠で IdP へ問い合わせて続けるため（ADR-0104）。枠の中の往復は発行者
  （例 ``identity.``）からログイン画面の名前（例 ``assay.``）へ移るので、発行者 1 つでは足りない。
  IdP を使わない構成では ``'self'`` だけ。
- ``/docs``・``/redoc`` は外の CDN からスクリプトを読むので **CSP だけ付けない**
  （他のヘッダは付ける）。
- **HSTS** は ``SESSION_COOKIE_SECURE`` が有効なとき（＝ https で配っているとき）だけ。
  http の開発で付けても意味が無く、付けた名前で https を強いるのは配る側の約束だから。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.kernel.settings.settings import settings

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
STRICT_TRANSPORT_SECURITY = "max-age=31536000"
#: これ以下の段の名前（``localhost``・``example.com``）は親を取らない
_BARE_NAME_LABELS = 2


def frame_sources(issuer: str) -> str:
    """``frame-src`` の値（ADR-0104）。発行者の名前から 1 つ上の親を許す。読めなければ ``'self'`` だけ。

    ``https://identity.nolumia.com/<テナント>`` → ``'self' https://*.nolumia.com``。名前が 2 段以下
    （``localhost``・``example.com``）なら、その名前のオリジンだけを足す。
    """
    parts = urlsplit(issuer)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "'self'"
    labels = parts.hostname.split(".")
    host = f"*.{'.'.join(labels[1:])}" if len(labels) > _BARE_NAME_LABELS else parts.hostname
    port = f":{parts.port}" if parts.port else ""
    return f"'self' {parts.scheme}://{host}{port}"


def content_security_policy(issuer: str) -> str:
    """全体の CSP。``frame-src`` だけ IdP の設定で変わる。"""
    return f"{CONTENT_SECURITY_POLICY}; frame-src {frame_sources(issuer)}"


#: 外の CDN を読む API 文書の画面。CSP だけ外す
_DOCUMENTATION_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})

_ALWAYS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # 再設定のリンク（``?token=``）を開いた画面から、外へ URL を漏らさない
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # ⚠ 設定は**応答の前に**読む。後で読むと、設定の読み直しが要求の DB の書き込みより
        #   先に接続を返し、確定前の書き込みを巻き戻すことがある（接続を共有する SQLite）
        served_over_https = settings.session_cookie_secure
        policy = content_security_policy(settings.oidc_issuer if settings.oidc_enabled else "")
        response = await call_next(request)
        for name, value in _ALWAYS.items():
            response.headers.setdefault(name, value)
        if request.url.path not in _DOCUMENTATION_PATHS:
            # 個別の応答が自分の CSP を持つ（より厳しい）なら、それを残す
            response.headers.setdefault("Content-Security-Policy", policy)
        if served_over_https:
            response.headers.setdefault("Strict-Transport-Security", STRICT_TRANSPORT_SECURITY)
        return response


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "STRICT_TRANSPORT_SECURITY",
    "SecurityHeadersMiddleware",
    "content_security_policy",
    "frame_sources",
]
