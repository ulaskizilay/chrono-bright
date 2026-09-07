"""Centralised logging configuration for ChronoBright.

All modules should obtain their logger via:

    from chronobright.logger import get_logger
    logger = get_logger(__name__)
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from chronobright import config

_configured = False


def _configure_root_logger() -> None:
    """Set up the root logger once on first use."""
    root = logging.getLogger("chronobright")
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    try:
        log_dir = config.get_log_dir()
        log_path = config.get_log_path()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        root.warning("Could not open log file. File logging is disabled.")


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        _configure_root_logger()
        _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger scoped under the 'chronobright' namespace."""
    _ensure_configured()
    if not name.startswith("chronobright"):
        name = f"chronobright.{name}"
    return logging.getLogger(name)
