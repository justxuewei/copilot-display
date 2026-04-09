from pathlib import Path as _Path

__version__ = (_Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()


from copilot_display import templates  # noqa: E402, F401
