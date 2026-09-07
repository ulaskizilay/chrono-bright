"""Application-wide constants, platform-aware paths, and shared validators."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ChronoBright"
APP_TITLE = "ChronoBright"
WINDOW_SIZE = "700x580"
WINDOW_MIN_WIDTH = 640
WINDOW_MIN_HEIGHT = 520

# Accent colors used across the UI (morning amber, evening indigo).
MORNING_ACCENT = "#f59e0b"
EVENING_ACCENT = "#6366f1"

APPEARANCE_MODE = "System"
APPEARANCE_OPTIONS: tuple[str, ...] = ("System", "Light", "Dark")
DEFAULT_APPEARANCE = "System"
COLOR_THEME = "dark-blue"


def normalize_appearance(value: object) -> str:
    """Return a supported appearance mode, defaulting safely to System."""
    if isinstance(value, str):
        for option in APPEARANCE_OPTIONS:
            if value.lower() == option.lower():
                return option
    return DEFAULT_APPEARANCE

DEFAULT_MORNING_TIME = "08:00"
DEFAULT_EVENING_TIME = "19:00"
DEFAULT_MORNING_BRIGHTNESS = 90
DEFAULT_EVENING_BRIGHTNESS = 80

# 0% means a black screen the user may not recover from without help.
# The schedule model still accepts 0-100 for compatibility, but the UI
# clamps manual input to this minimum.
MIN_BRIGHTNESS = 10
MAX_BRIGHTNESS = 100


def _resolve_base_dir() -> Path:
    """Return the Windows AppData Roaming directory for user data."""
    appdata = os.environ.get("APPDATA")
    return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"


def get_config_dir() -> Path:
    """Resolve the config dir dynamically (picks up APPDATA changes)."""
    return _resolve_base_dir() / APP_NAME


def get_log_dir() -> Path:
    return get_config_dir() / "logs"


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def get_log_path() -> Path:
    return get_log_dir() / "chronobright.log"


def get_lock_path() -> Path:
    return get_config_dir() / "chronobright.lock"


CONFIG_DIR: Path = _resolve_base_dir() / APP_NAME
LOG_DIR: Path = CONFIG_DIR / "logs"
USER_CONFIG_PATH: Path = CONFIG_DIR / "config.json"
LOG_PATH: Path = LOG_DIR / "chronobright.log"


def validate_brightness_level(level: object) -> None:
    """Reject levels that aren't plain integers in the 0–100 percent range.

    Booleans are explicitly rejected even though `bool` subclasses `int`, because
    ``True``/``False`` in a brightness field almost always indicates a bug in the
    caller (e.g. a missing type check on deserialised JSON).
    """
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 100:
        raise ValueError(f"Brightness must be an integer between 0 and 100: {level}")
