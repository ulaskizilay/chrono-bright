"""ChronoBright — scheduled display brightness control."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("chronobright")
except PackageNotFoundError:  # editable checkout without install, tests, etc.
    __version__ = "1.0.0"
