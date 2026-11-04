"""切れたログインを、画面を出さずに続ける往復の後始末（ADR-0104）。

画面（SPA）は見えない枠（iframe）を開き、``/api/auth/sso/login?frame=1`` から IdP へ ``prompt=none`` で
往復させる。戻り（``/callback``）は引き換え券を経ずに Cookie を載せ、**結果の頁**へ送る。画面は
枠の行き先（同じオリジン）を読んで結果を知る ——枠の中でスクリプトを動かさないので、CSP の
``script-src 'self'`` を緩めずに済む。

結果は 3 つ。

- ``renewed`` —— 続けられた（新しいアクセストークンの Cookie が載った）
- ``declined`` —— IdP で入っていない・許可が無い・別の人に入れ替わっていた。画面はログイン画面へ送る
- ``failed`` —— 往復が壊れた（往復状態が読めない・IdP と話せない）。画面はログイン画面へ送る

⚠ **枠に入れてよいのは自分のオリジンだけ。** 往復の口（``/login``・``/callback``）と結果の頁は
``frame-ancestors 'self'`` を付ける。ほかの応答はこれまでどおり ``'none'``（ADR-0073 §5）。
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlencode

from fastapi import Response
from fastapi.responses import HTMLResponse

#: 結果の頁。画面（``frontend/src/services/silentRenewal.ts``）と対で合わせる
RESULT_PATH = "/api/auth/sso/renewed"
RESULT_PARAM = "result"

#: 枠の中で開く応答の CSP。結果の頁は何も読み込まない
_FRAMED_CSP = "default-src 'none'; frame-ancestors 'self'"


class RenewalResult(StrEnum):
    RENEWED = "renewed"
    DECLINED = "declined"
    FAILED = "failed"


def allow_same_origin_framing(response: Response) -> Response:
    """自分のオリジンの枠にだけ入れてよい印を付ける（全体の守りのヘッダは ``setdefault`` なので残る）。"""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = _FRAMED_CSP
    return response


def result_location(result: RenewalResult) -> str:
    """結果の頁の URL。"""
    return f"{RESULT_PATH}?{urlencode({RESULT_PARAM: result.value})}"


def result_page() -> HTMLResponse:
    """結果の頁。中身は要らない（画面が読むのは URL だけ）。"""
    response = HTMLResponse("<!doctype html><title>sso</title>", headers={"Cache-Control": "no-store"})
    allow_same_origin_framing(response)
    return response


__all__ = ["RESULT_PATH", "RenewalResult", "allow_same_origin_framing", "result_location", "result_page"]
