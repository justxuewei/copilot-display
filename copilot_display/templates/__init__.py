"""Template registry for copilot-display.

Usage
-----
from copilot_display import templates

img = templates.get("stock").render({"symbol": "AAPL", "price": 189.30, "change": 1.20, "change_pct": 0.64})
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from copilot_display.templates.base import Template

if TYPE_CHECKING:
    pass

_registry: dict[str, Template] = {}


def register(template: Template) -> None:
    """Add *template* to the registry under its name."""
    _registry[template.name] = template


def get(name: str) -> Template | None:
    """Return the template registered under *name*, or None."""
    return _registry.get(name)


def list_names() -> list[str]:
    """Return all registered template names."""
    return sorted(_registry.keys())


# ── Register built-in templates ───────────────────────────────────────────────
from copilot_display.templates.stock import StockTemplate  # noqa: E402
from copilot_display.templates.text import TextTemplate  # noqa: E402

register(TextTemplate())
register(StockTemplate())
