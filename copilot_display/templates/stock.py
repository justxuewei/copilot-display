"""Stock real-time price template for the tri-color e-ink display."""
from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from copilot_display.render import COLOR_MAP, PADDING_X, PADDING_Y, SCREEN_H, SCREEN_W, load_font
from copilot_display.templates.base import Template


class StockTemplate(Template):
    """Renders a stock price card optimised for the 400×300 tri-color display.

    Required data keys:
        symbol (str)   — ticker symbol, e.g. "AAPL"
        price  (float) — current price

    Optional data keys:
        change      (float) — absolute price change (signed)
        change_pct  (float) — percentage change (signed, e.g. -0.97 means -0.97%)
        currency    (str)   — currency code shown before the price (default "USD")
        label       (str)   — small subtitle shown below the symbol (e.g. "NASDAQ")
    """

    name = "stock"

    def render(self, data: dict[str, Any]) -> Image.Image:
        if "symbol" not in data:
            raise ValueError("'symbol' is required for the stock template")
        if "price" not in data:
            raise ValueError("'price' is required for the stock template")

        symbol: str = str(data["symbol"]).upper()
        price: float = float(data["price"])
        change: float | None = float(data["change"]) if "change" in data else None
        change_pct: float | None = float(data["change_pct"]) if "change_pct" in data else None
        currency: str = str(data.get("currency", "USD"))
        label: str | None = str(data["label"]) if "label" in data else None

        img = Image.new("RGB", (SCREEN_W, SCREEN_H), COLOR_MAP["white"])
        draw = ImageDraw.Draw(img)

        usable_w = SCREEN_W - 2 * PADDING_X
        y = PADDING_Y

        # ── Symbol ──────────────────────────────────────────────────────────
        sym_font = load_font(38)
        sym_bbox = draw.textbbox((0, 0), symbol, font=sym_font)
        sym_w = sym_bbox[2] - sym_bbox[0]
        sym_h = sym_bbox[3] - sym_bbox[1]
        draw.text(
            (PADDING_X + (usable_w - sym_w) // 2, y),
            symbol,
            fill=COLOR_MAP["black"],
            font=sym_font,
        )
        y += sym_h

        # Optional exchange/label (small, below symbol)
        if label:
            lbl_font = load_font(14)
            lbl_bbox = draw.textbbox((0, 0), label, font=lbl_font)
            lbl_w = lbl_bbox[2] - lbl_bbox[0]
            draw.text(
                (PADDING_X + (usable_w - lbl_w) // 2, y + 2),
                label,
                fill=COLOR_MAP["black"],
                font=lbl_font,
            )
            y += lbl_bbox[3] - lbl_bbox[1] + 4

        # ── Separator ───────────────────────────────────────────────────────
        y += 6
        draw.line([(PADDING_X, y), (SCREEN_W - PADDING_X, y)], fill=COLOR_MAP["red"], width=2)
        y += 10

        # ── Price ───────────────────────────────────────────────────────────
        # Reserve ~60 px at the bottom for the change row
        change_row_h = 50 if (change is not None or change_pct is not None) else 0
        price_area_h = SCREEN_H - y - PADDING_Y - change_row_h

        price_str = f"{currency} {price:,.2f}"
        price_font = self._fit_single_line(draw, price_str, usable_w, price_area_h, 64, 18)
        price_bbox = draw.textbbox((0, 0), price_str, font=price_font)
        price_w = price_bbox[2] - price_bbox[0]
        price_h = price_bbox[3] - price_bbox[1]
        # Vertically center price in its zone
        price_y = y + (price_area_h - price_h) // 2
        draw.text(
            (PADDING_X + (usable_w - price_w) // 2, price_y),
            price_str,
            fill=COLOR_MAP["black"],
            font=price_font,
        )
        y = price_y + price_h + 8

        # ── Change row ──────────────────────────────────────────────────────
        if change is not None or change_pct is not None:
            parts: list[str] = []
            if change is not None:
                sign = "+" if change >= 0 else ""
                parts.append(f"{sign}{change:,.2f}")
            if change_pct is not None:
                sign = "+" if change_pct >= 0 else ""
                parts.append(f"({sign}{change_pct:.2f}%)")
            change_str = "  ".join(parts)

            is_loss = (change is not None and change < 0) or (
                change is None and change_pct is not None and change_pct < 0
            )
            change_color = COLOR_MAP["red"] if is_loss else COLOR_MAP["black"]

            change_font = self._fit_single_line(draw, change_str, usable_w, change_row_h, 28, 12)
            change_bbox = draw.textbbox((0, 0), change_str, font=change_font)
            change_w = change_bbox[2] - change_bbox[0]
            draw.text(
                (PADDING_X + (usable_w - change_w) // 2, y),
                change_str,
                fill=change_color,
                font=change_font,
            )

        return img

    @staticmethod
    def _fit_single_line(
        draw: ImageDraw.ImageDraw,
        text: str,
        max_width: int,
        max_height: int,
        size_max: int,
        size_min: int,
    ) -> Any:
        """Return the largest font that fits *text* on one line within the box."""
        for size in range(size_max, size_min - 1, -2):
            font = load_font(size)
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width and bbox[3] - bbox[1] <= max_height:
                return font
        return load_font(size_min)
