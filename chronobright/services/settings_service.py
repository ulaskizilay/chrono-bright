"""Persist and restore user schedule configuration to disk."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from chronobright import config
from chronobright.config import normalize_appearance, validate_brightness_level
from chronobright.i18n import DEFAULT_LANGUAGE, LanguageCode, normalize_language
from chronobright.logger import get_logger
from chronobright.models import BrightnessScheduleConfig

logger = get_logger(__name__)

_DEFAULT_APPEARANCE = config.DEFAULT_APPEARANCE


@dataclass(frozen=True)
class SettingsLoadResult:
    """Outcome of a settings load operation."""

    config: BrightnessScheduleConfig
    source: str  # "saved" | "fallback" | "missing"
    language: LanguageCode = DEFAULT_LANGUAGE
    appearance: str = _DEFAULT_APPEARANCE


class SettingsService:
    """Read and write schedule configuration to a JSON file on disk."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path if config_path is not None else config.get_config_path()

    def load_schedule(self) -> SettingsLoadResult:
        """Load the schedule from disk.

        Returns a :class:`SettingsLoadResult` whose *source* field indicates
        whether the data came from a saved file, defaults due to a missing file,
        or defaults due to a corrupt/invalid file.
        """
        if not self._config_path.exists():
            logger.info("No config file found at %s — using defaults.", self._config_path)
            return SettingsLoadResult(config=self._default_config(), source="missing")

        try:
            with self._config_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)

            schedule_config = BrightnessScheduleConfig(
                morning_time=str(payload["morning_time"]),
                morning_brightness=self._parse_brightness(payload["morning_brightness"]),
                evening_time=str(payload["evening_time"]),
                evening_brightness=self._parse_brightness(payload["evening_brightness"]),
            )
            schedule_config = self._clamp_to_safe_minimum(schedule_config)
            language = normalize_language(payload.get("language", DEFAULT_LANGUAGE))
            appearance = normalize_appearance(payload.get("appearance", config.DEFAULT_APPEARANCE))
            logger.info("Loaded schedule from %s.", self._config_path)
            return SettingsLoadResult(
                config=schedule_config, source="saved", language=language, appearance=appearance
            )

        except (OSError, TypeError, ValueError, KeyError) as exc:
            logger.warning(
                "Failed to load config from %s: %s. Falling back to defaults.",
                self._config_path,
                exc,
            )
            language = self._best_effort_language()
            appearance = self._best_effort_appearance()
            self._backup_corrupt_file()
            return SettingsLoadResult(
                config=self._default_config(),
                source="fallback",
                language=language,
                appearance=appearance,
            )

    def _best_effort_language(self) -> LanguageCode:
        """Try to preserve the saved language even when the schedule is corrupt."""
        try:
            with self._config_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                return normalize_language(payload.get("language", DEFAULT_LANGUAGE))
        except Exception:
            pass
        return DEFAULT_LANGUAGE

    def _best_effort_appearance(self) -> str:
        """Try to preserve the saved theme even when the schedule is corrupt."""
        try:
            with self._config_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                return normalize_appearance(payload.get("appearance", config.DEFAULT_APPEARANCE))
        except Exception:
            pass
        return config.DEFAULT_APPEARANCE

    def _backup_corrupt_file(self) -> None:
        """Keep a copy of the corrupt file for manual recovery."""
        try:
            backup = self._config_path.with_suffix(".json.corrupt.bak")
            backup.write_bytes(self._config_path.read_bytes())
            logger.info("Backed up corrupt config to %s.", backup)
        except OSError:
            logger.warning("Could not back up corrupt config file.")

    def save_schedule(
        self,
        schedule_config: BrightnessScheduleConfig,
        language: object = DEFAULT_LANGUAGE,
        appearance: object = None,
    ) -> None:
        """Validate and persist *schedule_config* to disk atomically.

        Raises:
            ValueError: If *schedule_config* contains invalid values.
            OSError: If the config file cannot be written.
        """
        schedule_config.validate()

        if appearance is None:
            appearance = self._best_effort_appearance()
        payload = {
            "morning_time": schedule_config.morning_time,
            "morning_brightness": schedule_config.morning_brightness,
            "evening_time": schedule_config.evening_time,
            "evening_brightness": schedule_config.evening_brightness,
            "language": normalize_language(language),
            "appearance": normalize_appearance(appearance),
        }

        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._config_path.with_suffix(".json.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp_path, self._config_path)
        except Exception:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise

        logger.info("Schedule saved to %s.", self._config_path)

    @staticmethod
    def _parse_brightness(value: object) -> int:
        """Parse a JSON brightness value, rejecting bools before ``int()`` coercion."""
        validate_brightness_level(value)
        if not isinstance(value, int):
            raise ValueError(f"Brightness must be an integer between 0 and 100: {value}")
        return value

    @staticmethod
    def _clamp_to_safe_minimum(cfg: BrightnessScheduleConfig) -> BrightnessScheduleConfig:
        """Clamp legacy 0-9% values up to MIN_BRIGHTNESS so old files never black out."""
        if cfg.morning_brightness >= config.MIN_BRIGHTNESS and (
            cfg.evening_brightness >= config.MIN_BRIGHTNESS
        ):
            return cfg
        logger.warning(
            "Clamping unsafe brightness (morning=%d, evening=%d) to minimum %d%%.",
            cfg.morning_brightness,
            cfg.evening_brightness,
            config.MIN_BRIGHTNESS,
        )
        return BrightnessScheduleConfig(
            morning_time=cfg.morning_time,
            morning_brightness=max(cfg.morning_brightness, config.MIN_BRIGHTNESS),
            evening_time=cfg.evening_time,
            evening_brightness=max(cfg.evening_brightness, config.MIN_BRIGHTNESS),
        )

    @staticmethod
    def _default_config() -> BrightnessScheduleConfig:
        return BrightnessScheduleConfig(
            morning_time=config.DEFAULT_MORNING_TIME,
            morning_brightness=config.DEFAULT_MORNING_BRIGHTNESS,
            evening_time=config.DEFAULT_EVENING_TIME,
            evening_brightness=config.DEFAULT_EVENING_BRIGHTNESS,
        )
