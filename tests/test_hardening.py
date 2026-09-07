"""Tests for hardening fixes: lock, clamping, period keys, backups."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from chronobright import config
from chronobright.single_instance import SingleInstanceLock
from chronobright.ui.app import ChronoBrightApp


def test_config_dynamic_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.get_config_dir() == tmp_path / "ChronoBright"
    assert config.get_log_dir() == tmp_path / "ChronoBright" / "logs"
    assert config.get_config_path().name == "config.json"
    assert config.get_log_path().name == "chronobright.log"
    assert config.get_lock_path().name == "chronobright.lock"
    assert config.MIN_BRIGHTNESS == 10


def test_single_instance_acquire_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "chronobright.lock"
    first = SingleInstanceLock(lock_path)
    assert first.acquire() is True
    second = SingleInstanceLock(lock_path)
    assert second.acquire() is False
    first.release()
    assert not lock_path.exists()
    # Re-acquire after release works.
    third = SingleInstanceLock(lock_path)
    assert third.acquire() is True
    third.release()


def test_normalize_period_key_variants() -> None:
    assert ChronoBrightApp._normalize_period_key("morning") == "morning"
    assert ChronoBrightApp._normalize_period_key("Morning") == "morning"
    assert ChronoBrightApp._normalize_period_key("Morning (immediate)") == "morning"
    assert ChronoBrightApp._normalize_period_key("evening") == "evening"
    assert ChronoBrightApp._normalize_period_key("Evening") == "evening"
    assert ChronoBrightApp._normalize_period_key("bogus") == "morning"
    assert ChronoBrightApp._normalize_period_key(None) == "morning"
    assert ChronoBrightApp._normalize_period_key("") == "morning"


def test_corrupt_config_preserves_language_and_backs_up(
    tmp_path: Path,
) -> None:
    from chronobright.services.settings_service import SettingsService

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "morning_time": "08:00",
                "morning_brightness": True,  # corrupt
                "evening_time": "19:00",
                "evening_brightness": 80,
                "language": "tr",
            }
        ),
        encoding="utf-8",
    )
    svc = SettingsService(config_path=cfg_path)
    result = svc.load_schedule()
    assert result.source == "fallback"
    assert result.language == "tr"
    assert cfg_path.with_suffix(".json.corrupt.bak").exists()


def test_brightness_display_validation() -> None:
    from chronobright.services.brightness_service import BrightnessService

    svc = BrightnessService()
    import pytest

    with pytest.raises(ValueError):
        svc.set_brightness(50, display=-1)


def test_run_on_ui_thread_enqueues_without_touching_tk() -> None:
    import queue

    app = ChronoBrightApp.__new__(ChronoBrightApp)
    app._is_exiting = False
    app._ui_queue = queue.Queue()
    app.after = MagicMock(side_effect=AssertionError("must not touch Tk from worker"))

    # Should not raise and must not call after().
    ChronoBrightApp._run_on_ui_thread(app, lambda: None)
    assert app._ui_queue.qsize() == 1
    app.after.assert_not_called()

    # Exiting apps drop work silently.
    app._is_exiting = True
    ChronoBrightApp._run_on_ui_thread(app, lambda: None)
    assert app._ui_queue.qsize() == 1


def test_legacy_brightness_clamped_on_load(tmp_path: Path) -> None:
    import json

    from chronobright.services.settings_service import SettingsService

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "morning_time": "08:00",
                "morning_brightness": 0,
                "evening_time": "19:00",
                "evening_brightness": 5,
                "language": "en",
            }
        ),
        encoding="utf-8",
    )
    result = SettingsService(config_path=cfg_path).load_schedule()
    assert result.source == "saved"
    assert result.config.morning_brightness == config.MIN_BRIGHTNESS
    assert result.config.evening_brightness == config.MIN_BRIGHTNESS


def test_seconds_until_next_change_bounds() -> None:
    from datetime import datetime

    from chronobright.time_utils import seconds_until_next_change

    secs = seconds_until_next_change("08:00", "19:00", datetime(2026, 1, 15, 10, 0))
    assert 1.0 <= secs <= 15 * 60.0

    # Right before a boundary -> small positive sleep.
    secs = seconds_until_next_change("08:00", "19:00", datetime(2026, 1, 15, 18, 59, 30))
    assert 1.0 <= secs <= 60.0


def test_adaptive_sleep_wakes_early_on_new_schedule() -> None:
    from chronobright.models import BrightnessScheduleConfig
    from chronobright.services.schedule_service import ScheduleService

    svc = ScheduleService(on_brightness_change=MagicMock(), poll_interval_seconds=60.0)
    assert svc._sleep_interval() == 60.0  # no config yet
    svc.apply_schedule(
        BrightnessScheduleConfig(
            morning_time="08:00",
            morning_brightness=90,
            evening_time="19:00",
            evening_brightness=80,
        )
    )
    # apply_schedule signals the loop to recompute its sleep.
    assert svc._wakeup.is_set()
    assert 1.0 <= svc._sleep_interval() <= 60.0
    svc.start()
    try:
        assert svc._thread is not None and svc._thread.is_alive()
    finally:
        svc.stop()


def test_autostart_service_without_winreg(monkeypatch) -> None:
    import sys

    import pytest

    from chronobright.services.autostart_service import AutostartService

    monkeypatch.delitem(sys.modules, "winreg", raising=False)
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("No module named 'winreg'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    svc = AutostartService()
    assert svc.is_enabled() is False
    with pytest.raises(RuntimeError):
        svc.enable()


def test_tray_uses_visibility_provider() -> None:
    from chronobright.services.tray_service import TrayService

    svc = TrayService(
        on_show_window=MagicMock(),
        on_hide_window=MagicMock(),
        on_exit_application=MagicMock(),
        is_window_visible=lambda: False,
    )
    assert svc._can_show_window(MagicMock()) is True
    assert svc._can_hide_window(MagicMock()) is False

    svc.set_active_period("morning", 90)
    assert svc._tray_title() != "ChronoBright"
