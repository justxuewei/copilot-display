"""Stock watchlist template for the tri-color e-ink display.

Row format:
    AAPL  [████░░░░░░]  189.30  +0.75%
    CODE   progress bar   LAST   CHG%

Header uses the same fixed font size as data rows (red, no divider).

Data schema
-----------
{
    "stocks": [
        {
            "symbol":     "AAPL",
            "low":        185.00,   # day low  (used for bar position)
            "price":      189.30,   # current / last price
            "high":       195.00,   # day high (used for bar position)
            "change_pct": 0.75      # optional  (+0.75 means +0.75%)
        },
        ...
    ],
    "updated_at": "14:32"           # optional — defaults to current HH:MM
}
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw

from copilot_display.render import COLOR_MAP, PADDING_X, PADDING_Y, SCREEN_H, SCREEN_W, load_font
from copilot_display.templates.base import Template

# ── Fixed layout constants ────────────────────────────────────────────────────
_FONT_SIZE      = 13
_BAR_LEFT       = 75               # bar left edge (55 px code slot + gap)
_BAR_W          = 55               # bar width
_BAR_RIGHT      = _BAR_LEFT + _BAR_W   # 130
_X_PRICE_RIGHT  = 252              # price right-aligned here
_X_RIGHT        = SCREEN_W - PADDING_X  # 380  (change% + timestamp)
_BAR_H          = 5                # bar rectangle height


class StockTemplate(Template):
    name = "stock"

    def render(self, data: dict[str, Any]) -> Image.Image:
        stocks = data.get("stocks")
        if not stocks:
            raise ValueError("'stocks' list is required and must not be empty")
        updated_at = str(data.get("updated_at") or datetime.now().strftime("%H:%M"))

        img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_MAP["white"])
        draw = ImageDraw.Draw(img)

        font   = load_font(_FONT_SIZE)
        line_h = draw.textbbox((0, 0), "A", font=font)[3]
        row_h  = line_h + 3

        # ── Timestamp (bottom-right, smaller font) ────────────────────────────
        ts_font = load_font(10)
        ts_h    = draw.textbbox((0, 0), "A", font=ts_font)[3]
        ts_y    = SCREEN_H - PADDING_Y - ts_h
        ts_w    = draw.textbbox((0, 0), updated_at, font=ts_font)[2]
        draw.text((_X_RIGHT - ts_w, ts_y), updated_at,
                  fill=COLOR_MAP["black"], font=ts_font)

        # ── How many rows fit above the timestamp ─────────────────────────────
        available_h = ts_y - PADDING_Y - 2
        max_rows    = available_h // row_h - 1   # -1 for header

        y = PADDING_Y

        # ── Header ───────────────────────────────────────────────────────────
        red = COLOR_MAP["red"]

        draw.text((PADDING_X, y), "CODE", fill=red, font=font)

        # empty bar outline
        bt = y + (line_h - _BAR_H) // 2
        draw.rectangle([_BAR_LEFT, bt, _BAR_RIGHT, bt + _BAR_H - 1],
                       outline=COLOR_MAP["black"])

        last_w = draw.textbbox((0, 0), "LAST", font=font)[2]
        draw.text((_X_PRICE_RIGHT - last_w, y), "LAST", fill=red, font=font)

        chg_w = draw.textbbox((0, 0), "CHG%", font=font)[2]
        draw.text((_X_RIGHT - chg_w, y), "CHG%", fill=red, font=font)

        y += row_h

        # ── Data rows ─────────────────────────────────────────────────────────
        for stock in stocks[:max_rows]:
            symbol     = str(stock.get("symbol", "?")).upper()
            price      = float(stock["price"])
            low        = float(stock.get("low", price))
            high       = float(stock.get("high", price))
            change_pct = stock.get("change_pct")

            # Symbol
            draw.text((PADDING_X, y), symbol,
                      fill=COLOR_MAP["black"], font=font)

            # Progress bar
            bt     = y + (line_h - _BAR_H) // 2
            pos    = (price - low) / (high - low) if high > low else 0.0
            pos    = max(0.0, min(1.0, pos))
            filled = max(1, round(pos * _BAR_W))

            draw.rectangle([_BAR_LEFT, bt, _BAR_LEFT + filled - 1, bt + _BAR_H - 1],
                           fill=COLOR_MAP["black"])
            if filled < _BAR_W:
                draw.rectangle([_BAR_LEFT + filled, bt, _BAR_RIGHT, bt + _BAR_H - 1],
                               outline=COLOR_MAP["black"])

            # Current price (always 2 dp, right-aligned)
            price_str = f"{price:,.2f}"
            pw        = draw.textbbox((0, 0), price_str, font=font)[2]
            draw.text((_X_PRICE_RIGHT - pw, y), price_str,
                      fill=COLOR_MAP["black"], font=font)

            # Change % (right-aligned, red if loss)
            if change_pct is not None:
                sign   = "+" if float(change_pct) >= 0 else ""
                chg    = f"{sign}{float(change_pct):.2f}%"
                color  = COLOR_MAP["red"] if float(change_pct) < 0 else COLOR_MAP["black"]
                cw     = draw.textbbox((0, 0), chg, font=font)[2]
                draw.text((_X_RIGHT - cw, y), chg, fill=color, font=font)

            y += row_h

        return img
