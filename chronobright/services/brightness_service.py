"""Thin wrapper around screen-brightness-control for reading and writing display brightness."""

from __future__ import annotations

import screen_brightness_control as sbc

from chronobright.config import validate_brightness_level
from chronobright.logger import get_logger

logger = get_logger(__name__)


class BrightnessService:
    """Read and set the system display brightness."""

    def get_all_brightness(self) -> list[int] | None:
        """Return per-display brightness levels, or None on failure."""
        try:
            result = sbc.get_brightness()
        except Exception as exc:
            logger.warning("Could not read current brightness: %s", exc)
            return None

        if isinstance(result, list):
            if not result:
                logger.warning("Brightness query returned an empty list.")
                return None
            return [int(level) for level in result]

        return [int(result)]

    def get_brightness(self) -> int | None:
        """Return the primary display brightness as an integer percentage, or None on failure."""
        levels = self.get_all_brightness()
        if levels is None:
            return None
        return levels[0]

    def set_brightness(self, level: int, display: int | None = None) -> None:
        """Set display brightness to *level* percent (0–100).

        Args:
            level: Target brightness in percent.
            display: Optional display index (0-based) to target a single monitor.
                When ``None`` (default), all detected displays are set to *level* —
                matching ``screen_brightness_control.set_brightness`` semantics.

        Raises:
            ValueError: If *level* is not a valid brightness percentage.
            RuntimeError: If the underlying brightness API call fails.
        """
        validate_brightness_level(level)
        if display is not None and (not isinstance(display, int) or display < 0):
            raise ValueError(f"Display index must be a non-negative integer: {display}")
        try:
            if display is None:
                sbc.set_brightness(level)
            else:
                sbc.set_brightness(level, display=display)
            if display is None:
                logger.debug("Brightness set to %d%% for all displays.", level)
            else:
                logger.debug("Brightness set to %d%% on display %d.", level, display)
        except Exception as exc:
            target = "all displays" if display is None else f"display {display}"
            raise RuntimeError(f"Failed to set brightness to {level}% on {target}") from exc
