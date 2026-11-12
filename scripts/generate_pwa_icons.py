"""Generate the PWA icons (`frontend/public/`).

This script (colors and shape coordinates) is the source of truth for the icons; the outputs are
committed as generated files. PNGs are written with the standard library only, so no extra
dependency or external rasterizer is needed (same result in CI and locally).

    uv run python scripts/generate_pwa_icons.py

Outputs:
    favicon.svg                  browser tab (rounded corners, vector)
    pwa-192x192.png              regular manifest icon
    pwa-512x512.png              same (large)
    pwa-maskable-512x512.png     maskable (full bleed, smaller shape within the safe zone)
    apple-touch-icon.png         iOS home screen (full bleed, since the OS rounds the corners)

The in-app mark (header and pre-sign-in screens; `frontend/src/components/AppMark.tsx`) also
loads favicon.svg as is. To change the design or colors, edit only this script and regenerate;
don't redraw the same picture on the frontend side.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import NamedTuple

# Output directory. Served as frontend static assets.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"

# Colors. A diagonal gradient that brackets the theme's --accent (#4f46e5).
GRADIENT_START = (0x63, 0x66, 0xF1)
GRADIENT_END = (0x43, 0x38, 0xCA)
MARK_COLOR = (0xFF, 0xFF, 0xFF)

# Corner radius (as a ratio of the side length).
CORNER_RADIUS_RATIO = 0.22

# Lightning-bolt mark. Defined in a 100x100 coordinate space and scaled to each icon size.
MARK_POINTS = ((62.0, 4.0), (20.0, 56.0), (46.0, 56.0), (38.0, 96.0), (80.0, 44.0), (54.0, 44.0))
MARK_BOX = (20.0, 4.0, 80.0, 96.0)  # bounding box of the points above (x0, y0, x1, y1)

# Samples per pixel axis (supersampling for anti-aliasing).
SAMPLES_PER_AXIS = 4


class IconSpec(NamedTuple):
    """Spec of one PNG to generate."""

    filename: str
    size: int
    mark_height_ratio: float
    rounded: bool


ICONS = (
    # Regular icons: rounded corners with transparent corners.
    IconSpec("pwa-192x192.png", 192, 0.62, rounded=True),
    IconSpec("pwa-512x512.png", 512, 0.62, rounded=True),
    # maskable: the OS crops it to a circle etc. Keep the shape in the central 50% and fill the background.
    IconSpec("pwa-maskable-512x512.png", 512, 0.42, rounded=False),
    # iOS rounds the corners itself, so no transparent corners.
    IconSpec("apple-touch-icon.png", 180, 0.58, rounded=False),
)


def _scaled_mark(size: int, height_ratio: float) -> tuple[tuple[float, float], ...]:
    """Convert the mark's points to coordinates centered in an icon of side *size*."""
    box_x0, box_y0, box_x1, box_y1 = MARK_BOX
    scale = size * height_ratio / (box_y1 - box_y0)
    offset_x = (size - (box_x1 - box_x0) * scale) / 2 - box_x0 * scale
    offset_y = (size - (box_y1 - box_y0) * scale) / 2 - box_y0 * scale
    return tuple((x * scale + offset_x, y * scale + offset_y) for x, y in MARK_POINTS)


def _inside_polygon(points: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    """Whether point (*x*, *y*) is inside the polygon (crossing-number test)."""
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
    """Whether point (*x*, *y*) is inside a rounded square of side *size* and corner radius *radius*."""
    near_x = min(max(x, radius), size - radius)
    near_y = min(max(y, radius), size - radius)
    if x == near_x or y == near_y:  # straight part along an edge (not outside a corner)
        return 0.0 <= x <= size and 0.0 <= y <= size
    return (x - near_x) ** 2 + (y - near_y) ** 2 <= radius**2


def _mix(start: int, end: int, ratio: float) -> int:
    return round(start + (end - start) * ratio)


def _background_color(size: int, x: float, y: float) -> tuple[int, int, int]:
    """Diagonal gradient color: GRADIENT_START at top-left, GRADIENT_END at bottom-right."""
    ratio = (x + y) / (size * 2)
    return (
        _mix(GRADIENT_START[0], GRADIENT_END[0], ratio),
        _mix(GRADIENT_START[1], GRADIENT_END[1], ratio),
        _mix(GRADIENT_START[2], GRADIENT_END[2], ratio),
    )


def _sample(spec: IconSpec, mark: tuple[tuple[float, float], ...], x: float, y: float) -> tuple[int, int, int, int]:
    """Color of one sample: transparent outside the background, white inside the mark."""
    if spec.rounded and not _inside_rounded_square(spec.size, spec.size * CORNER_RADIUS_RATIO, x, y):
        return (0, 0, 0, 0)
    if _inside_polygon(mark, x, y):
        return (*MARK_COLOR, 255)
    return (*_background_color(spec.size, x, y), 255)


# Sample positions within a pixel (a grid offset to cell centers).
_SAMPLE_OFFSETS = tuple((index + 0.5) / SAMPLES_PER_AXIS for index in range(SAMPLES_PER_AXIS))


def _pixel(spec: IconSpec, mark: tuple[tuple[float, float], ...], column: int, row: int) -> bytes:
    """RGBA of one pixel, anti-aliased by averaging the samples."""
    red = green = blue = alpha = 0
    for offset_y in _SAMPLE_OFFSETS:
        for offset_x in _SAMPLE_OFFSETS:
            # Accumulate alpha-premultiplied colors (so transparent areas' color doesn't bleed into edges).
            sample = _sample(spec, mark, column + offset_x, row + offset_y)
            red += sample[0] * sample[3]
            green += sample[1] * sample[3]
            blue += sample[2] * sample[3]
            alpha += sample[3]
    if alpha == 0:
        return bytes(4)
    return bytes((round(red / alpha), round(green / alpha), round(blue / alpha), round(alpha / SAMPLES_PER_AXIS**2)))


def _pixel_row(spec: IconSpec, mark: tuple[tuple[float, float], ...], row: int) -> bytearray:
    """RGBA bytes for one row."""
    line = bytearray()
    for column in range(spec.size):
        line += _pixel(spec, mark, column, row)
    return line


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """A PNG chunk (length + type + payload + CRC)."""
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_png(path: Path, size: int, rows: list[bytearray]) -> None:
    """Write RGBA rows as an 8-bit/channel PNG."""
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)  # filter type 0 (None) for every row
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _render(spec: IconSpec) -> None:
    """Generate and write one icon."""
    mark = _scaled_mark(spec.size, spec.mark_height_ratio)
    rows = [_pixel_row(spec, mark, row) for row in range(spec.size)]
    _write_png(OUTPUT_DIR / spec.filename, spec.size, rows)
    print(f"[icons] {spec.filename} ({spec.size}x{spec.size})")


def _hex_color(color: tuple[int, int, int]) -> str:
    red, green, blue = color
    return f"#{red:02x}{green:02x}{blue:02x}"


def _write_favicon_svg() -> None:
    """favicon.svg for the tab. Writes the same colors, shape and layout as the PNGs as a vector."""
    canvas = 512
    mark_height_ratio = ICONS[0].mark_height_ratio  # match the regular icons' size
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in _scaled_mark(canvas, mark_height_ratio))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas} {canvas}">
  <!-- Generated by scripts/generate_pwa_icons.py. Do not edit by hand. -->
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
