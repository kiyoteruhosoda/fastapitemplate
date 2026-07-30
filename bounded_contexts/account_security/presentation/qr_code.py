"""QR コードの描画。

TOTP の ``otpauth://`` URI を認証アプリに読ませるための表示用。SVG で描くため
画像ライブラリ（Pillow）に依存せず、拡大しても粗くならない。
"""

from __future__ import annotations

import base64
import io

import qrcode
from qrcode.image.svg import SvgPathImage


def render_qr_code_data_uri(value: str) -> str:
    """*value* を符号化した QR コードを SVG の data URI で返す。"""
    buffer = io.BytesIO()
    qrcode.make(value, image_factory=SvgPathImage).save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


__all__ = ["render_qr_code_data_uri"]
