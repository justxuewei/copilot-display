"""Stock watchlist template for the tri-color e-ink display.

Renders a pre-formatted box-drawing text block using Fira Code (monospace),
centered on the 400×300 image.

    ┌─────────────────────────────────────┐
    │ Copilot Display                     │
    ├─────────────────────────────────────┤
    │ AAPL              10000.01(+12.43%) │
    │ [░░░░░░░░█░░░░░░░░░░░░░░░░░░░░░░░░] │
    ├─────────────────────────────────────┤
    │ TSLA                242.50(-1.26%)  │
    │ [░░░░░░░░░░░░░░░░░░░░█░░░░░░░░░░░░] │
    └─────────────────────────────────────┘

Data schema
-----------
{
    "stocks": [
        {
            "symbol":     "AAPL",
            "low":        185.00,
            "price":      189.30,
            "high":       195.00,
            "change_pct": 0.75      # optional
        },
        ...
    ],
    "updated_at": "14:32"           # optional — shown in header as "at HH:MM"
}
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

import yfinance as yf

from copilot_display.render import COLOR_MAP, SCREEN_H, SCREEN_W
from copilot_display.templates.base import Template

_FONT_PATH = "/usr/share/fonts/truetype/cascadia-code/CascadiaMono.ttf"
_FONT_SIZE = 16

logger = logging.getLogger("copilot_display.stock")

DEFAULT_SYMBOLS = ["^IXIC", "^GSPC", "GC=F", "BZ=F"]

# Friendly display names for common tickers
_DISPLAY_NAMES: dict[str, str] = {
    "^IXIC": "NASDAQ",
    "^GSPC": "S&P 500",
    "^DJI": "DOW",
    "GC=F": "GOLD",
    "SI=F": "SILVER",
    "BZ=F": "BRENT",
    "CL=F": "WTI",
    "BTC-USD": "BTC",
    "ETH-USD": "ETH",
}


def fetch_quotes(symbols: list[str] | None = None) -> dict:
    """Return stock template-compatible data dict for the given symbols.

    Returns
    -------
    dict with keys ``stocks`` (list) and ``updated_at`` (str HH:MM).
    Each stock entry has: symbol, price, low, high, change_pct.
    """
    symbols = (symbols or DEFAULT_SYMBOLS)[:4]
    stocks: list[dict] = []

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            high = info.get("dayHigh") or info.get("regularMarketDayHigh")
            low = info.get("dayLow") or info.get("regularMarketDayLow")
            prev_close = info.get("previousClose") or info.get(
                "regularMarketPreviousClose"
            )

            if price is None:
                continue

            change_pct = None
            if prev_close and prev_close != 0:
                change_pct = round((price - prev_close) / prev_close * 100, 2)

            display_name = _DISPLAY_NAMES.get(sym, info.get("shortName", sym))

            stocks.append(
                {
                    "symbol": display_name,
                    "price": price,
                    "low": low or price,
                    "high": high or price,
                    "change_pct": change_pct,
                }
            )
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", sym, exc)
            continue

    if not stocks:
        raise RuntimeError(f"Could not fetch data for any of: {symbols}")

    return {
        "stocks": stocks,
        "updated_at": datetime.now().strftime("%H:%M"),
    }


class StockTemplate(Template):
    name = "stock"

    def fetch(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract ticker symbols from data and fetch live quotes."""
        symbols = [data.get(f"sym{i}") for i in range(1, 5)]
        symbols = [s for s in symbols if s] or DEFAULT_SYMBOLS
        return fetch_quotes(symbols)

    def render(self, data: dict[str, Any]) -> Image.Image:
        stocks = data.get("stocks")
        if not stocks:
            raise ValueError("'stocks' list is required and must not be empty")
        updated_at = str(data.get("updated_at") or datetime.now().strftime("%H:%M"))

        img  = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_MAP["white"])
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(_FONT_PATH, _FONT_SIZE)

        # Monospace char width — all glyphs same advance
        char_w = draw.textbbox((0, 0), "X", font=font)[2]

        # Box outer width in chars so the block fits with small margin
        box_w = (SCREEN_W - 16) // char_w   # e.g. (400-16)//10 = 38

        # Find the max number of stocks whose rendered block fits vertically
        for n in range(min(len(stocks), 6), 0, -1):
            text = self._build(stocks[:n], box_w, updated_at)
            bb   = draw.textbbox((0, 0), text, font=font)
            if (bb[3] - bb[1]) <= SCREEN_H - 10:
                break

        # Center on canvas
        x = (SCREEN_W - (bb[2] - bb[0])) // 2 - bb[0]
        y = (SCREEN_H - (bb[3] - bb[1])) // 2 - bb[1]
        draw.text((x, y), text, fill=COLOR_MAP["black"], font=font)
        return img

    @staticmethod
    def _build(stocks: list[dict], box_w: int, updated_at: str = "") -> str:
        inner_w   = box_w - 2          # chars between corners
        content_w = box_w - 4          # chars between "│ " and " │"
        bar_inner = content_w - 2      # chars inside [ ]

        def row(content: str) -> str:
            return f"│ {content:<{content_w}} │"

        lines: list[str] = []
        ts = f"at {updated_at}" if updated_at else ""
        title = "Copilot Display"
        header = f"{title}{ts:>{content_w - len(title)}}"
        lines.append("┌" + "─" * inner_w + "┐")
        lines.append(row(header))

        for i, stock in enumerate(stocks):
            lines.append("├" + "─" * inner_w + "┤")

            symbol     = str(stock.get("symbol", "?")).upper()
            price      = float(stock["price"])
            low        = float(stock.get("low", price))
            high       = float(stock.get("high", price))
            change_pct = stock.get("change_pct")

            price_str = f"{price:,.2f}"
            if change_pct is not None:
                sign  = "+" if float(change_pct) >= 0 else ""
                right = f"{price_str}({sign}{float(change_pct):.2f}%)"
            else:
                right = price_str

            # Truncate symbol if price string leaves no room
            sym_w = content_w - len(right)
            sym   = symbol[:max(0, sym_w)].ljust(max(0, sym_w))
            lines.append(f"│ {sym}{right} │")

            # Progress bar
            pos = (price - low) / (high - low) if high > low else 0.5
            pos = max(0.0, min(1.0, pos))
            idx = max(0, min(bar_inner - 1, round(pos * (bar_inner - 1))))
            bar = "[" + "=" * idx + "█" + "=" * (bar_inner - 1 - idx) + "]"
            lines.append(row(bar))

        lines.append("└" + "─" * inner_w + "┘")
        return "\n".join(lines)
