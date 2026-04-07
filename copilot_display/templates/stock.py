"""Stock watchlist template for the tri-color e-ink display.

Renders a compact multi-row table:

    CODE     LAST        CHANGE
    ──────────────────────────────────
    AAPL   189.30    +1.20 (+0.64%)
    TSLA   242.50   -3.10 (-1.26%)
    ...
                            14:32

Data schema
-----------
{
    "stocks": [
        {"symbol": "AAPL", "price": 189.30, "change": 1.20, "change_pct": 0.64},
        ...
    ],
    "updated_at": "14:32"   # optional — defaults to current HH:MM
}
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw

from copilot_display.render import COLOR_MAP, PADDING_X, PADDING_Y, SCREEN_H, SCREEN_W, load_font
from copilot_display.templates.base import Template

# Column right-edge x-positions (within the 400×300 canvas)
_X_CODE        = PADDING_X           # left edge of CODE (left-aligned)
_X_LAST_RIGHT  = PADDING_X + 180     # right edge of LAST column
_X_CHANGE_RIGHT = SCREEN_W - PADDING_X  # right edge of CHANGE column


class StockTemplate(Template):
    name = "stock"

    def render(self, data: dict[str, Any]) -> Image.Image:
        stocks = data.get("stocks")
        if not stocks:
            raise ValueError("'stocks' list is required and must not be empty")
        updated_at: str = str(data.get("updated_at") or datetime.now().strftime("%H:%M"))

        img = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_MAP["white"])
        draw = ImageDraw.Draw(img)

        # ── Header ──────────────────────────────────────────────────────────
        hdr_font = load_font(13)
        hdr_h = draw.textbbox((0, 0), "A", font=hdr_font)[3]
        y = PADDING_Y

        self._draw_row(draw, "CODE", "LAST", "CHANGE", y, hdr_font,
                       COLOR_MAP["red"], COLOR_MAP["red"], COLOR_MAP["red"])
        y += hdr_h + 4

        draw.line([(PADDING_X, y), (SCREEN_W - PADDING_X, y)],
                  fill=COLOR_MAP["black"], width=1)
        y += 5

        # ── Reserve space for timestamp at bottom ───────────────────────────
        ts_font = load_font(10)
        ts_h    = draw.textbbox((0, 0), "A", font=ts_font)[3]
        ts_y    = SCREEN_H - PADDING_Y - ts_h
        available_h = ts_y - y - 4

        # ── Auto-fit row font so all stocks fit ─────────────────────────────
        n = len(stocks)
        row_font = load_font(9)   # fallback minimum
        row_h    = 0
        for size in range(16, 8, -1):
            font   = load_font(size)
            line_h = draw.textbbox((0, 0), "A", font=font)[3]
            gap    = max(2, size // 6)           # small inter-row gap
            if (line_h + gap) * n <= available_h:
                row_font = font
                row_h    = line_h + gap
                break
        if row_h == 0:
            # More stocks than fit — truncate to however many do
            line_h = draw.textbbox((0, 0), "A", font=row_font)[3]
            row_h  = line_h + 2

        # ── Rows ────────────────────────────────────────────────────────────
        max_rows = min(n, available_h // row_h)
        for stock in stocks[:max_rows]:
            symbol     = str(stock.get("symbol", "?")).upper()
            price      = stock.get("price")
            change     = stock.get("change")
            change_pct = stock.get("change_pct")

            price_str  = f"{float(price):,.2f}" if price is not None else "—"
            change_str = self._fmt_change(change, change_pct)

            is_loss = (
                (change is not None and float(change) < 0)
                or (change is None and change_pct is not None and float(change_pct) < 0)
            )
            chg_color = COLOR_MAP["red"] if is_loss else COLOR_MAP["black"]

            self._draw_row(draw, symbol, price_str, change_str, y,
                           row_font, COLOR_MAP["black"], COLOR_MAP["black"], chg_color)
            y += row_h

        # ── Timestamp ───────────────────────────────────────────────────────
        ts_bbox = draw.textbbox((0, 0), updated_at, font=ts_font)
        ts_w    = ts_bbox[2] - ts_bbox[0]
        draw.text((SCREEN_W - PADDING_X - ts_w, ts_y),
                  updated_at, fill=COLOR_MAP["black"], font=ts_font)

        return img

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_row(
        draw: ImageDraw.ImageDraw,
        code: str,
        last: str,
        change: str,
        y: int,
        font: Any,
        code_color: tuple,
        last_color: tuple,
        change_color: tuple,
    ) -> None:
        """Draw one table row with CODE left-aligned, LAST and CHANGE right-aligned."""
        draw.text((_X_CODE, y), code, fill=code_color, font=font)

        last_w = draw.textbbox((0, 0), last, font=font)[2]
        draw.text((_X_LAST_RIGHT - last_w, y), last, fill=last_color, font=font)

        chg_w = draw.textbbox((0, 0), change, font=font)[2]
        draw.text((_X_CHANGE_RIGHT - chg_w, y), change, fill=change_color, font=font)

    @staticmethod
    def _fmt_change(change: Any, change_pct: Any) -> str:
        c   = float(change)     if change     is not None else None
        pct = float(change_pct) if change_pct is not None else None
        if c is not None and pct is not None:
            sign = "+" if c >= 0 else ""
            return f"{sign}{c:.2f} ({sign}{pct:.2f}%)"
        if c is not None:
            sign = "+" if c >= 0 else ""
            return f"{sign}{c:.2f}"
        if pct is not None:
            sign = "+" if pct >= 0 else ""
            return f"{sign}{pct:.2f}%"
        return "—"
