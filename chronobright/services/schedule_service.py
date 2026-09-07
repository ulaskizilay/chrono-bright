"""Background scheduler that applies brightness levels at configured times."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from chronobright.logger import get_logger
from chronobright.models import BrightnessScheduleConfig
from chronobright.time_utils import is_morning_period_active, seconds_until_next_change

logger = get_logger(__name__)

PeriodName = Literal["morning", "evening"]


class ScheduleService:
    """Manage a daily brightness schedule running in a daemon thread.

    Period transitions are detected by polling the active schedule window instead
    of firing one-shot wall-clock jobs. This avoids duplicate or skipped triggers
    during daylight-saving time changes.
    """

    def __init__(
        self,
        on_brightness_change: Callable[[int, str], None],
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._on_brightness_change = on_brightness_change
        self._poll_interval_seconds = poll_interval_seconds
        self._running = threading.Event()
        self._wakeup = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._config: BrightnessScheduleConfig | None = None
        self._active_period: PeriodName | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread. No-op if already running."""
        if self._thread and self._thread.is_alive():
            return

        self._running.set()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Schedule service started.")

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it to finish."""
        self._running.clear()
        self._wakeup.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Schedule service stopped.")

    @property
    def job_count(self) -> int:
        """Number of configured schedule transitions (morning + evening)."""
        with self._lock:
            return 2 if self._config is not None else 0

    @property
    def active_period(self) -> PeriodName | None:
        """Currently active schedule period, if a schedule is loaded."""
        with self._lock:
            return self._active_period

    def replace_brightness_callback(self, callback: Callable[[int, str], None]) -> None:
        """Swap the brightness-change callback."""
        with self._lock:
            self._on_brightness_change = callback

    def apply_schedule(self, config: BrightnessScheduleConfig) -> str:
        """Validate *config*, store it, and immediately apply the correct period.

        The config is stored even if the immediate brightness call fails, so a
        transient display error never leaves the scheduler without a schedule.

        Returns a human-readable status string describing the active schedule.
        """
        config.validate()
        with self._lock:
            self._config = config
        self._wakeup.set()
        self._apply_immediate_brightness(config)

        status = (
            f"Schedule active — morning {config.morning_time} @ {config.morning_brightness}%, "
            f"evening {config.evening_time} @ {config.evening_brightness}%"
        )
        logger.info(status)
        return status

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_immediate_brightness(self, config: BrightnessScheduleConfig) -> None:
        """Apply whichever period is currently active without waiting for a poll tick."""
        period = self._current_period(config)
        with self._lock:
            self._active_period = period
            callback = self._on_brightness_change
        level = self._period_settings(config, period)[0]
        logger.debug("Immediate apply: %s period active.", period)
        try:
            callback(level, period)
        except Exception:
            logger.exception("Immediate brightness apply failed, schedule kept")

    def _sleep_interval(self) -> float:
        """Adaptive sleep: next boundary or poll interval, whichever is sooner."""
        with self._lock:
            cfg = self._config
        if cfg is None:
            return self._poll_interval_seconds
        try:
            adaptive = seconds_until_next_change(
                cfg.morning_time, cfg.evening_time, datetime.now()
            )
        except Exception:
            return self._poll_interval_seconds
        # Check at least every poll interval so a 1s-configured test loop stays
        # responsive, but sleep longer when the next change is far away.
        # Cap each nap at 60s so manual clock changes are picked up promptly.
        return max(self._poll_interval_seconds, min(adaptive, 60.0))

    def _run_loop(self) -> None:
        while self._running.is_set():
            try:
                self._check_period_transition()
            except Exception:
                # Never kill the scheduler on a transient error; keep polling.
                logger.exception("Schedule loop error, continuing")
            self._wakeup.clear()
            # Wake early on stop() or apply_schedule(), else sleep adaptively.
            self._wakeup.wait(timeout=self._sleep_interval())

    def _check_period_transition(self) -> None:
        with self._lock:
            config = self._config
            active = self._active_period
            callback = self._on_brightness_change
        if config is None:
            return

        try:
            period = self._current_period(config)
        except Exception:
            logger.exception("Failed to compute current period")
            return
        if period == active:
            return

        with self._lock:
            self._active_period = period
        level = self._period_settings(config, period)[0]
        logger.info("Schedule period changed to %s.", period)
        try:
            callback(level, period)
        except Exception:
            logger.exception("Scheduled brightness apply failed, keeping new period")

    @staticmethod
    def _current_period(config: BrightnessScheduleConfig) -> PeriodName:
        now = datetime.now().time()
        if is_morning_period_active(config.morning_time, config.evening_time, now):
            return "morning"
        return "evening"

    @staticmethod
    def _period_settings(config: BrightnessScheduleConfig, period: PeriodName) -> tuple[int, PeriodName]:
        if period == "morning":
            return config.morning_brightness, "morning"
        return config.evening_brightness, "evening"
