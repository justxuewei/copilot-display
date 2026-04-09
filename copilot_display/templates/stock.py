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

import requests
from bs4 import BeautifulSoup
import yfinance as yf

from copilot_display.render import COLOR_MAP, SCREEN_H, SCREEN_W
from pathlib import Path
from copilot_display.templates.base import Template

_FONT_PATH = str(Path(__file__).parent.parent / "fonts" / "CascadiaMono.ttf")
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


def _parse_symbols(raw: list[str]) -> tuple[list[str], set[str]]:
    """Parse symbol list, extracting (top) markers.

    Returns (clean_symbols, top_symbols) where clean_symbols has the (top)
    suffix stripped and top_symbols is the set of symbols that must be shown.

    Raises ValueError if more than 4 symbols are marked (top).
    """
    clean: list[str] = []
    top: set[str] = set()
    for entry in raw:
        entry = entry.strip()
        if not entry:
            continue
        if entry.lower().endswith("(top)"):
            sym = entry[: -len("(top)")].strip()
            clean.append(sym)
            top.add(sym)
        else:
            clean.append(entry)
    if len(top) > 4:
        raise ValueError(
            f"Too many (top) symbols ({len(top)}); at most 4 are allowed."
        )
    return clean, top


def _fetch_yahoo_overnight(sym: str) -> tuple[float | None, float | None]:
    """Scrape the active overnight price directly from Yahoo Finance."""
    url = f"https://finance.yahoo.com/quote/{sym}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml"
    }
    price = None
    change_pct = None
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        badge = soup.find('span', class_=lambda c: c and 'OVERNIGHT' in c.split())
        if badge and badge.parent:
            price_span = badge.parent.find('span')
            if price_span:
                price = float(price_span.text.strip().replace(',', ''))
        
        pct_span = soup.find('span', attrs={"data-testid": "qsp-overnight-price-change-percent"})
        if pct_span:
            text = pct_span.text.strip().replace('(', '').replace(')', '').replace('%', '').replace('+', '')
            change_pct = float(text)
    except Exception as exc:
        logger.warning("Overnight scrape failed for %s: %s", sym, exc)
    return price, change_pct


def _fetch_one(sym: str) -> dict | None:
    """Fetch a single ticker from Yahoo Finance. Returns None on failure."""
    try:
        ticker = yf.Ticker(sym)
        info = ticker.info

        market_state = (info.get("marketState") or "").upper()  # PRE, REGULAR, POST, CLOSED

        regular_price = info.get("currentPrice") or info.get("regularMarketPrice")
        pre_price  = info.get("preMarketPrice")
        post_price = info.get("postMarketPrice")

        overnight_scraped_pct: float | None = None

        is_scraped = False

        if market_state == "PRE" and pre_price:
            price = pre_price
            price_label = "PRE"
        elif market_state in ("POST", "POSTPOST", "CLOSED") and post_price:
            price = post_price
            price_label = "POST"
        elif market_state == "PREPRE":
            # Attempt to scrape overnight Blue Ocean data
            scraped_price, scraped_pct = _fetch_yahoo_overnight(sym)
            if scraped_price is not None:
                price = scraped_price
                overnight_scraped_pct = scraped_pct
                price_label = "O/N"
                is_scraped = True
            elif post_price:
                price = post_price
                price_label = ""
            else:
                price = regular_price
                price_label = ""
        else:
            price = regular_price
            price_label = ""

        if is_scraped:
            logger.info("Fetched data for %s directly from Yahoo Finance webpage (Overnight).", sym)
        else:
            logger.info("Fetched data for %s using yfinance API (market_state: %s).", sym, market_state)

        if price is None:
            price = regular_price
        if price is None:
            return None

        high = info.get("dayHigh") or info.get("regularMarketDayHigh")
        low = info.get("dayLow") or info.get("regularMarketDayLow")
        prev_close = info.get("previousClose") or info.get(
            "regularMarketPreviousClose"
        )

        # Use the session-specific change percent from yfinance when available,
        # so PRE shows only the pre-market move, POST shows only the post-market
        # move, and REGULAR shows the intraday move from previous close.
        raw_pct: float | None = None
        if market_state == "PRE" and pre_price:
            raw_pct = info.get("preMarketChangePercent")
        elif market_state in ("POST", "POSTPOST", "CLOSED") and post_price:
            raw_pct = info.get("postMarketChangePercent")
        else:
            raw_pct = info.get("regularMarketChangePercent")

        if raw_pct is not None:
            # yfinance returns the value already as a percentage (e.g. 0.75 = 0.75%)
            change_pct = round(float(raw_pct), 2)
        elif prev_close and prev_close != 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)
        else:
            change_pct = None

        display_name = _DISPLAY_NAMES.get(sym, sym)

        if price_label == "O/N":
            if overnight_scraped_pct is not None:
                change_pct = overnight_scraped_pct
            elif regular_price and regular_price != 0:
                # Recompute change percentage relative to regular close if overnight
                change_pct = round((price - regular_price) / regular_price * 100, 2)
            
            low = price - 10
            high = price + 10

        return {
            "symbol": display_name,
            "_raw_sym": sym,
            "price": price,
            "price_label": price_label,
            "low": low or price,
            "high": high or price,
            "change_pct": change_pct,
        }
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", sym, exc)
        return None


def fetch_quotes(symbols: list[str] | None = None) -> dict:
    """Return stock template-compatible data dict for the given symbols.

    Symbols may carry a ``(top)`` suffix to mark them as always-visible.
    If more than 4 symbols are provided, all are fetched and then filtered:
    - (top) symbols are always included (error if > 4 top symbols)
    - remaining slots (up to 4 total) filled by highest absolute % change

    Returns
    -------
    dict with keys ``stocks`` (list) and ``updated_at`` (str HH:MM).
    Each stock entry has: symbol, price, low, high, change_pct.
    """
    raw = symbols or DEFAULT_SYMBOLS
    clean_syms, top_syms = _parse_symbols(raw)

    # Fetch all
    fetched: list[dict] = []
    for sym in clean_syms:
        entry = _fetch_one(sym)
        if entry is not None:
            fetched.append(entry)

    if not fetched:
        raise RuntimeError(f"Could not fetch data for any of: {clean_syms}")

    # Select up to 4 to display
    if len(fetched) <= 4:
        selected = fetched
    else:
        pinned = [e for e in fetched if e["_raw_sym"] in top_syms]
        regular = [e for e in fetched if e["_raw_sym"] not in top_syms]
        slots = 4 - len(pinned)
        regular_sorted = sorted(
            regular,
            key=lambda e: abs(e["change_pct"]) if e["change_pct"] is not None else 0,
            reverse=True,
        )
        selected = pinned + regular_sorted[:slots]

    # Strip internal key before returning
    stocks = [{k: v for k, v in e.items() if k != "_raw_sym"} for e in selected]

    return {
        "stocks": stocks,
        "updated_at": datetime.now().strftime("%H:%M"),
    }


class StockTemplate(Template):
    name = "stock"

    def fetch(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract ticker symbols from data and fetch live quotes.

        Accepts either:
        - ``symbols`` key: comma-separated string or list of ticker codes
        - Legacy ``sym1``..``sym4`` keys (for backwards compatibility)

        Ticker codes may carry a ``(top)`` suffix to mark them as always shown.
        """
        if "symbols" in data:
            raw = data["symbols"]
            if isinstance(raw, str):
                symbols = [s.strip() for s in raw.split(",") if s.strip()]
            else:
                symbols = list(raw)
        else:
            symbols = [data.get(f"sym{i}") for i in range(1, 5)]
            symbols = [s for s in symbols if s]
        return fetch_quotes(symbols or DEFAULT_SYMBOLS)

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

            symbol      = str(stock.get("symbol", "?")).upper()
            price       = float(stock["price"])
            low         = float(stock.get("low", price))
            high        = float(stock.get("high", price))
            change_pct  = stock.get("change_pct")
            price_label = str(stock.get("price_label") or "")

            # Append (PRE)/(POST) label to symbol when in extended hours
            if price_label:
                symbol = f"{symbol}({price_label})"

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
