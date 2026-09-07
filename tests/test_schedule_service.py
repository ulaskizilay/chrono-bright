"""Tests for :mod:`chronobright.services.schedule_service`."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from chronobright.models import BrightnessScheduleConfig
from chronobright.services.schedule_service import ScheduleService


@pytest.fixture
def callback() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(callback: MagicMock) -> ScheduleService:
    return ScheduleService(on_brightness_change=callback, poll_interval_seconds=0.01)


def test_apply_schedule_registers_active_config(service: ScheduleService, callback: MagicMock) -> None:
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )
    with patch.object(service, "_apply_immediate_brightness"):
        status = service.apply_schedule(config)

    assert service.job_count == 2
    assert service._config is config
    assert "Schedule active" in status
    callback.assert_not_called()


@patch("chronobright.services.schedule_service.datetime")
def test_apply_immediate_brightness_morning_period(
    mock_datetime: MagicMock,
    service: ScheduleService,
    callback: MagicMock,
) -> None:
    mock_datetime.now.return_value = datetime(2026, 1, 15, 10, 0)
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )

    service._apply_immediate_brightness(config)

    callback.assert_called_once_with(90, "morning")
    assert service.active_period == "morning"


@patch("chronobright.services.schedule_service.datetime")
def test_apply_immediate_brightness_evening_period(
    mock_datetime: MagicMock,
    service: ScheduleService,
    callback: MagicMock,
) -> None:
    mock_datetime.now.return_value = datetime(2026, 1, 15, 21, 0)
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )

    service._apply_immediate_brightness(config)

    callback.assert_called_once_with(80, "evening")
    assert service.active_period == "evening"


@patch("chronobright.services.schedule_service.datetime")
def test_apply_immediate_brightness_overnight_schedule(
    mock_datetime: MagicMock,
    service: ScheduleService,
    callback: MagicMock,
) -> None:
    mock_datetime.now.return_value = datetime(2026, 1, 15, 23, 0)
    config = BrightnessScheduleConfig(
        morning_time="22:00",
        morning_brightness=90,
        evening_time="06:00",
        evening_brightness=80,
    )

    service._apply_immediate_brightness(config)

    callback.assert_called_once_with(90, "morning")


@patch("chronobright.services.schedule_service.datetime")
def test_check_period_transition_fires_once_on_boundary_crossing(
    mock_datetime: MagicMock,
    service: ScheduleService,
    callback: MagicMock,
) -> None:
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )
    service._config = config
    service._active_period = "morning"
    mock_datetime.now.return_value = datetime(2026, 3, 29, 19, 0)

    service._check_period_transition()
    service._check_period_transition()

    callback.assert_called_once_with(80, "evening")
    assert service.active_period == "evening"


@patch("chronobright.services.schedule_service.datetime")
def test_dst_repeated_hour_does_not_double_fire(
    mock_datetime: MagicMock,
    service: ScheduleService,
    callback: MagicMock,
) -> None:
    """Fall-back hour repeats 01:00, but period state prevents duplicate callbacks."""
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )
    service._config = config
    service._active_period = "evening"
    mock_datetime.now.return_value = datetime(2026, 11, 1, 1, 30)

    for _ in range(3):
        service._check_period_transition()

    callback.assert_not_called()
    assert service.active_period == "evening"


def test_start_and_stop_lifecycle(service: ScheduleService) -> None:
    service.start()
    assert service._thread is not None
    assert service._thread.is_alive()

    service.stop()
    service._thread.join(timeout=2.0)
    assert not service._thread.is_alive()


def test_start_is_noop_when_already_running(service: ScheduleService) -> None:
    service.start()
    first_thread = service._thread
    service.start()
    assert service._thread is first_thread
    service.stop()


def test_run_loop_continues_on_exception(service: ScheduleService) -> None:
    service._running.set()
    calls = {"count": 0}

    def flaky() -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        service._running.clear()

    with patch.object(service, "_check_period_transition", side_effect=flaky):
        service._run_loop()
    assert calls["count"] >= 2


def test_callback_exception_does_not_kill_scheduler(
    service: ScheduleService, callback: MagicMock
) -> None:
    callback.side_effect = RuntimeError("display offline")
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )
    # Immediate apply must not raise; config must still be stored.
    service.apply_schedule(config)
    assert service.job_count == 2

    service._active_period = "morning"
    with patch(
        "chronobright.services.schedule_service.datetime"
    ) as mock_datetime:
        from datetime import datetime as dt

        mock_datetime.now.return_value = dt(2026, 3, 29, 19, 0)
        service._check_period_transition()
    # Period advanced even though the callback failed.
    assert service.active_period == "evening"


def test_replace_brightness_callback(service: ScheduleService) -> None:
    new_callback = MagicMock()
    service.replace_brightness_callback(new_callback)
    config = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )
    with patch.object(service, "_apply_immediate_brightness"):
        service.apply_schedule(config)
    assert service._on_brightness_change is new_callback
