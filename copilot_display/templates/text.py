"""Plain text template — wraps the existing render_text function."""
from __future__ import annotations

from typing import Any

from PIL import Image

from copilot_display.render import render_text
from copilot_display.templates.base import Template


class TextTemplate(Template):
    """Renders a title + body using the default auto-fit text layout.

    Required data keys:
        body (str)

    Optional data keys:
        title (str)
        title_color ("red" | "black", default "red")
        body_color  ("red" | "black", default "black")
    """

    name = "text"

    def render(self, data: dict[str, Any]) -> Image.Image:
        if "body" not in data:
            raise ValueError("'body' is required for the text template")
        return render_text(
            body=data["body"],
            title=data.get("title"),
            title_color=data.get("title_color", "red"),
            body_color=data.get("body_color", "black"),
        )
