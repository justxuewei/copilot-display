"""Render text to a 400x300 tri-color image for the 4.2-inch e-ink display."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCREEN_W = 400
SCREEN_H = 300

PADDING_X = 20
PADDING_Y = 12

TITLE_SIZE_MAX = 40
TITLE_SIZE_MIN = 18
BODY_SIZE_MAX = 28
BODY_SIZE_MIN = 10

COLOR_MAP = {
    "red": (255, 0, 0),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
}

# Common font paths to try (CJK-capable)
_FONT_SEARCH_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
]

_cached_font_path: str | None = None


def _find_font_path() -> str | None:
    global _cached_font_path
    if _cached_font_path is not None:
        return _cached_font_path
    for p in _FONT_SEARCH_PATHS:
        if Path(p).exists():
            _cached_font_path = p
            return p
    return None


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font_path()
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _is_cjk(ch: str) -> bool:
    try:
        name = unicodedata.name(ch, "")
    except ValueError:
        return False
    return any(
        tag in name
        for tag in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "IDEOGRAPH")
    )


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels. CJK-aware."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width:
                if current:
                    lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    size_max: int,
    size_min: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Find the largest font size where text fits in the given area."""
    for size in range(size_max, size_min - 1, -1):
        font = load_font(size)
        wrapped = wrap_text(draw, text, font, max_width)
        line_h = draw.textbbox((0, 0), "Ag", font=font)[3]
        total_h = line_h * len(wrapped)
        if total_h <= max_height:
            return font, wrapped
    # Use minimum size regardless
    font = load_font(size_min)
    wrapped = wrap_text(draw, text, font, max_width)
    return font, wrapped


def render_text(
    body: str,
    title: str | None = None,
    title_color: str = "red",
    body_color: str = "black",
) -> Image.Image:
    """Render text to a 400x300 tri-color PIL Image."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_MAP["white"])
    draw = ImageDraw.Draw(img)

    tc = COLOR_MAP.get(title_color, COLOR_MAP["red"])
    bc = COLOR_MAP.get(body_color, COLOR_MAP["black"])

    usable_w = SCREEN_W - 2 * PADDING_X
    y = PADDING_Y

    if title:
        # Reserve up to 40% of height for title
        title_max_h = int((SCREEN_H - 2 * PADDING_Y) * 0.35)
        title_font, title_lines = fit_text(
            draw, title, usable_w, title_max_h, TITLE_SIZE_MAX, TITLE_SIZE_MIN
        )
        line_h = draw.textbbox((0, 0), "Ag", font=title_font)[3]
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = PADDING_X + usable_w // 2 - (bbox[0] + bbox[2]) // 2
            draw.text((x, y), line, fill=tc, font=title_font)
            y += line_h
        # Separator line
        y += 6
        draw.line([(PADDING_X, y), (SCREEN_W - PADDING_X, y)], fill=COLOR_MAP["red"], width=1)
        y += 8

    # Body
    body_max_h = SCREEN_H - y - PADDING_Y
    body_font, body_lines = fit_text(
        draw, body, usable_w, body_max_h, BODY_SIZE_MAX, BODY_SIZE_MIN
    )
    line_h = draw.textbbox((0, 0), "Ag", font=body_font)[3]
    for line in body_lines:
        draw.text((PADDING_X, y), line, fill=bc, font=body_font)
        y += line_h

    return img
