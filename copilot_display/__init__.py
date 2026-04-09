from importlib.metadata import version as _version, PackageNotFoundError as _PackageNotFoundError

try:
    __version__ = _version("copilot-display")
except _PackageNotFoundError:
    __version__ = "unknown"


from copilot_display import templates  # noqa: E402, F401
