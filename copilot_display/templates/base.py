"""Base class for display templates."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from PIL import Image


class Template(ABC):
    """A named template that renders structured data to a PIL Image."""

    name: str  # Must be set as a class attribute in every subclass

    @abstractmethod
    def render(self, data: dict[str, Any]) -> Image.Image:
        """Render *data* and return a 400×300 RGB image ready to push."""
        ...
