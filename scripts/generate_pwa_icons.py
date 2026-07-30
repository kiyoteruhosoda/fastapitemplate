"""PWA アイコン（`frontend/public/`）を生成する。

アイコンの正本はこのスクリプト（配色と図形の座標）であり、出力物は生成結果として
コミットする。標準ライブラリだけで PNG を書き出すため、追加の依存や外部の
ラスタライザは要らない（CI・手元のどちらでも同じ結果になる）。

    uv run python scripts/generate_pwa_icons.py

出力:
    favicon.svg                  ブラウザのタブ用（角丸・ベクタ）
    pwa-192x192.png              マニフェストの通常アイコン
    pwa-512x512.png              同（大）
    pwa-maskable-512x512.png     maskable 用（全面塗り・セーフゾーンを取った小さめの図形）
    apple-touch-icon.png         iOS ホーム画面用（OS 側で角丸に切られるため全面塗り）
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import NamedTuple

# 出力先。frontend の静的アセットとして配信される。
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"

# 配色。テーマの --accent (#4f46e5) を挟む形の対角グラデーション。
GRADIENT_START = (0x63, 0x66, 0xF1)
GRADIENT_END = (0x43, 0x38, 0xCA)
MARK_COLOR = (0xFF, 0xFF, 0xFF)

# 角丸の半径（辺の長さに対する比）。
CORNER_RADIUS_RATIO = 0.22

# 稲妻マーク。100x100 の座標系で定義し、各アイコンの大きさへ拡大縮小する。
MARK_POINTS = ((62.0, 4.0), (20.0, 56.0), (46.0, 56.0), (38.0, 96.0), (80.0, 44.0), (54.0, 44.0))
MARK_BOX = (20.0, 4.0, 80.0, 96.0)  # 上の点列の外接矩形 (x0, y0, x1, y1)

# 1 ピクセルあたりの走査点数（アンチエイリアス用のスーパーサンプリング）。
SAMPLES_PER_AXIS = 4


class IconSpec(NamedTuple):
    """生成する PNG 1 枚の仕様。"""

    filename: str
    size: int
    mark_height_ratio: float
    rounded: bool


ICONS = (
    # 通常アイコン: 角を透明にした角丸。
    IconSpec("pwa-192x192.png", 192, 0.62, rounded=True),
    IconSpec("pwa-512x512.png", 512, 0.62, rounded=True),
    # maskable: OS が円などに切り抜く。図形を中央 50% に収め、背景は全面塗りにする。
    IconSpec("pwa-maskable-512x512.png", 512, 0.42, rounded=False),
    # iOS は独自に角丸へ切るため、透明な角を持たせない。
    IconSpec("apple-touch-icon.png", 180, 0.58, rounded=False),
)


def _scaled_mark(size: int, height_ratio: float) -> tuple[tuple[float, float], ...]:
    """稲妻マークの点列を、一辺 *size* のアイコン中央に置いた座標へ変換する。"""
    box_x0, box_y0, box_x1, box_y1 = MARK_BOX
    scale = size * height_ratio / (box_y1 - box_y0)
    offset_x = (size - (box_x1 - box_x0) * scale) / 2 - box_x0 * scale
    offset_y = (size - (box_y1 - box_y0) * scale) / 2 - box_y0 * scale
    return tuple((x * scale + offset_x, y * scale + offset_y) for x, y in MARK_POINTS)


def _inside_polygon(points: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    """点 (*x*, *y*) が多角形の内側にあるか（交差数判定）。"""
    inside = False
    previous_x, previous_y = points[-1]
    for current_x, current_y in points:
        if (current_y > y) != (previous_y > y):
            crossing_x = current_x + (y - current_y) / (previous_y - current_y) * (previous_x - current_x)
            if x < crossing_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _inside_rounded_square(size: int, radius: float, x: float, y: float) -> bool:
    """点 (*x*, *y*) が一辺 *size*・角半径 *radius* の角丸正方形の内側にあるか。"""
    near_x = min(max(x, radius), size - radius)
    near_y = min(max(y, radius), size - radius)
    if x == near_x or y == near_y:  # 辺に沿った直線部分（角の外へは出ていない）
        return 0.0 <= x <= size and 0.0 <= y <= size
    return (x - near_x) ** 2 + (y - near_y) ** 2 <= radius**2


def _mix(start: int, end: int, ratio: float) -> int:
    return round(start + (end - start) * ratio)


def _background_color(size: int, x: float, y: float) -> tuple[int, int, int]:
    """対角グラデーションの色。左上を GRADIENT_START、右下を GRADIENT_END にする。"""
    ratio = (x + y) / (size * 2)
    return (
        _mix(GRADIENT_START[0], GRADIENT_END[0], ratio),
        _mix(GRADIENT_START[1], GRADIENT_END[1], ratio),
        _mix(GRADIENT_START[2], GRADIENT_END[2], ratio),
    )


def _sample(spec: IconSpec, mark: tuple[tuple[float, float], ...], x: float, y: float) -> tuple[int, int, int, int]:
    """1 走査点の色。背景の外側は透明、マークの内側は白。"""
    if spec.rounded and not _inside_rounded_square(spec.size, spec.size * CORNER_RADIUS_RATIO, x, y):
        return (0, 0, 0, 0)
    if _inside_polygon(mark, x, y):
        return (*MARK_COLOR, 255)
    return (*_background_color(spec.size, x, y), 255)


# 1 ピクセル内の走査点の位置（中心をずらした格子）。
_SAMPLE_OFFSETS = tuple((index + 0.5) / SAMPLES_PER_AXIS for index in range(SAMPLES_PER_AXIS))


def _pixel(spec: IconSpec, mark: tuple[tuple[float, float], ...], column: int, row: int) -> bytes:
    """1 ピクセルの RGBA。走査点の平均を取ってアンチエイリアスする。"""
    red = green = blue = alpha = 0
    for offset_y in _SAMPLE_OFFSETS:
        for offset_x in _SAMPLE_OFFSETS:
            # アルファを乗算した色で足し合わせる（透明部分の色が縁へ滲まないようにする）。
            sample = _sample(spec, mark, column + offset_x, row + offset_y)
            red += sample[0] * sample[3]
            green += sample[1] * sample[3]
            blue += sample[2] * sample[3]
            alpha += sample[3]
    if alpha == 0:
        return bytes(4)
    return bytes((round(red / alpha), round(green / alpha), round(blue / alpha), round(alpha / SAMPLES_PER_AXIS**2)))


def _pixel_row(spec: IconSpec, mark: tuple[tuple[float, float], ...], row: int) -> bytearray:
    """1 行分の RGBA バイト列。"""
    line = bytearray()
    for column in range(spec.size):
        line += _pixel(spec, mark, column, row)
    return line


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """PNG チャンク（長さ + 種別 + 中身 + CRC）。"""
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_png(path: Path, size: int, rows: list[bytearray]) -> None:
    """RGBA の行データを 8bit/channel の PNG として書き出す。"""
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)  # 各行のフィルタ種別は 0（None）
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _render(spec: IconSpec) -> None:
    """アイコン 1 枚を生成して書き出す。"""
    mark = _scaled_mark(spec.size, spec.mark_height_ratio)
    rows = [_pixel_row(spec, mark, row) for row in range(spec.size)]
    _write_png(OUTPUT_DIR / spec.filename, spec.size, rows)
    print(f"[icons] {spec.filename} ({spec.size}x{spec.size})")


def _hex_color(color: tuple[int, int, int]) -> str:
    red, green, blue = color
    return f"#{red:02x}{green:02x}{blue:02x}"


def _write_favicon_svg() -> None:
    """タブ用の favicon.svg。PNG と同じ配色・同じ図形・同じ配置をベクタで書き出す。"""
    canvas = 512
    mark_height_ratio = ICONS[0].mark_height_ratio  # 通常アイコンと同じ大きさに合わせる
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in _scaled_mark(canvas, mark_height_ratio))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}">
  <!-- scripts/generate_pwa_icons.py が生成する。手で編集しない。 -->
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{_hex_color(GRADIENT_START)}"/>
      <stop offset="1" stop-color="{_hex_color(GRADIENT_END)}"/>
    </linearGradient>
  </defs>
  <rect width="{canvas}" height="{canvas}" rx="{round(canvas * CORNER_RADIUS_RATIO)}" fill="url(#bg)"/>
  <polygon points="{points}" fill="{_hex_color(MARK_COLOR)}"/>
</svg>
"""
    (OUTPUT_DIR / "favicon.svg").write_text(svg, encoding="utf-8")
    print("[icons] favicon.svg")


def main() -> None:
    for spec in ICONS:
        _render(spec)
    _write_favicon_svg()


if __name__ == "__main__":
    main()
