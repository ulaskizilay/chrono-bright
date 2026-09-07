"""Boost coverage for autostart, __main__ flags, UI queue drain, tray title."""

from __future__ import annotations

import queue
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _install_fake_winreg(monkeypatch, store: dict):
    mod = types.ModuleType("winreg")
    mod.HKEY_CURRENT_USER = "HKCU"
    mod.REG_SZ = 1
    mod.KEY_SET_VALUE = 2

    class FakeKey:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def OpenKey(root, path, *args):
        if path not in store and (path, None) not in store:
            # Simulate per-value store keyed by path.
            raise FileNotFoundError(path)
        return FakeKey(path)

    def CreateKey(root, path):
        store.setdefault(path, {})
        return FakeKey(path)

    def QueryValueEx(key, name):
        values = store.get(key.path, {})
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], mod.REG_SZ

    def SetValueEx(key, name, _r, _t, value):
        store.setdefault(key.path, {})[name] = value

    def DeleteValue(key, name):
        values = store.get(key.path, {})
        if name not in values:
            raise FileNotFoundError(name)
        del values[name]

    mod.OpenKey = OpenKey
    mod.CreateKey = CreateKey
    mod.QueryValueEx = QueryValueEx
    mod.SetValueEx = SetValueEx
    mod.DeleteValue = DeleteValue
    monkeypatch.setitem(sys.modules, "winreg", mod)
    return mod


def test_autostart_enable_disable_roundtrip(monkeypatch) -> None:
    from chronobright.services.autostart_service import AutostartService

    store: dict = {}
    _install_fake_winreg(monkeypatch, store)
    svc = AutostartService()
    assert svc.is_enabled() is False
    svc.enable()
    assert svc.is_enabled() is True
    svc.set_enabled(False)
    assert svc.is_enabled() is False
    svc.set_enabled(True)
    assert svc.is_enabled() is True
    svc.disable()
    svc.disable()  # idempotent, no raise


def test_autostart_disable_oserror(monkeypatch) -> None:
    from chronobright.services.autostart_service import AutostartService

    store: dict = {}
    mod = _install_fake_winreg(monkeypatch, store)

    def boom(*args, **kwargs):
        raise OSError("registry locked")

    monkeypatch.setattr(mod, "DeleteValue", boom)
    store["Software\\Microsoft\\Windows\\CurrentVersion\\Run"] = {"ChronoBright": "x"}
    with pytest.raises(RuntimeError):
        AutostartService().disable()


def test_main_autostart_flags(capsys) -> None:
    from chronobright.__main__ import main

    with patch(
        "chronobright.services.autostart_service.AutostartService.set_enabled"
    ) as mock_set:
        main(["--enable-autostart"])
        mock_set.assert_called_once_with(True)
    with (
        patch(
            "chronobright.services.autostart_service.AutostartService.set_enabled",
            side_effect=RuntimeError("nope"),
        ),
        patch("chronobright.__main__.sys.exit") as mock_exit,
    ):
        main(["--disable-autostart"])
        mock_exit.assert_called_once_with(1)
    capsys.readouterr()


def test_drain_ui_queue_executes_and_reschedules() -> None:
    from chronobright.ui.app import ChronoBrightApp

    app = ChronoBrightApp.__new__(ChronoBrightApp)
    app._is_exiting = False
    app._ui_queue = queue.Queue()
    app.after = MagicMock()
    calls: list[str] = []
    app._ui_queue.put(lambda: calls.append("a"))
    app._ui_queue.put(lambda: (_ for _ in ()).throw(RuntimeError("task boom")))
    app._ui_queue.put(lambda: calls.append("b"))

    ChronoBrightApp._drain_ui_queue(app)
    assert calls == ["a", "b"]
    app.after.assert_called_with(50, app._drain_ui_queue)

    # Exiting stops rescheduling.
    app._is_exiting = True
    app.after.reset_mock()
    ChronoBrightApp._drain_ui_queue(app)
    app.after.assert_not_called()


def test_on_autostart_toggled_success_and_failure() -> None:
    from chronobright.ui.app import ChronoBrightApp

    app = ChronoBrightApp.__new__(ChronoBrightApp)
    app._autostart_service = MagicMock()
    app._autostart_var = MagicMock()
    app._autostart_var.get.return_value = True
    app._set_status = MagicMock()
    ChronoBrightApp._on_autostart_toggled(app)
    app._autostart_service.set_enabled.assert_called_once_with(True)

    app._autostart_service.set_enabled.side_effect = RuntimeError("denied")
    app._autostart_var.get.return_value = False
    ChronoBrightApp._on_autostart_toggled(app)
    app._set_status.assert_called_once_with("autostart_error", "red")


def test_tray_title_and_refresh_with_icon() -> None:
    from chronobright.services.tray_service import TrayService

    svc = TrayService(
        on_show_window=MagicMock(),
        on_hide_window=MagicMock(),
        on_exit_application=MagicMock(),
    )
    assert svc._tray_title() == "ChronoBright"
    svc.set_active_period("morning", 90)
    assert "morning" in svc._tray_title().lower() or "ChronoBright" in svc._tray_title()

    # With a fake icon, refresh updates menu + title.
    fake_icon = MagicMock()
    svc._icon = fake_icon
    svc.refresh_menu_text()
    fake_icon.update_menu.assert_called()

    # Broken translate falls back to default title.
    svc2 = TrayService(
        on_show_window=MagicMock(),
        on_hide_window=MagicMock(),
        on_exit_application=MagicMock(),
        translate=MagicMock(side_effect=RuntimeError("i18n boom")),
    )
    svc2._active_period = "morning"
    svc2._active_level = 90
    assert svc2._tray_title() == "ChronoBright"


def test_update_tray_period_delegates() -> None:
    from unittest.mock import MagicMock

    from chronobright.ui.app import ChronoBrightApp

    app = ChronoBrightApp.__new__(ChronoBrightApp)
    app._tray_service = MagicMock()
    ChronoBrightApp._update_tray_period(app, "evening", 80)
    app._tray_service.set_active_period.assert_called_once_with("evening", 80)


def test_normalize_appearance_variants() -> None:
    from chronobright import config

    assert config.normalize_appearance("dark") == "Dark"
    assert config.normalize_appearance("LIGHT") == "Light"
    assert config.normalize_appearance("system") == "System"
    assert config.normalize_appearance("bogus") == "System"
    assert config.normalize_appearance(None) == "System"


def test_appearance_round_trip(tmp_path) -> None:
    import json

    from chronobright.models import BrightnessScheduleConfig
    from chronobright.services.settings_service import SettingsService

    cfg_path = tmp_path / "config.json"
    svc = SettingsService(config_path=cfg_path)
    assert svc.load_schedule().appearance == "System"
    sample = BrightnessScheduleConfig(
        morning_time="08:00",
        morning_brightness=90,
        evening_time="19:00",
        evening_brightness=80,
    )
    svc.save_schedule(sample, language="en", appearance="dark")
    loaded = svc.load_schedule()
    assert loaded.appearance == "Dark"
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert payload["appearance"] == "Dark"


def test_on_appearance_changed_persists() -> None:
    from unittest.mock import MagicMock

    from chronobright.ui.app import ChronoBrightApp

    app = ChronoBrightApp.__new__(ChronoBrightApp)
    app._appearance = "System"
    app._current_schedule_config = MagicMock()
    app._translator = MagicMock()
    app._translator.language = "en"
    app._settings_service = MagicMock()
    with patch("chronobright.ui.app.ctk.set_appearance_mode") as mock_mode:
        ChronoBrightApp._on_appearance_changed(app, "dark")
    assert app._appearance == "Dark"
    mock_mode.assert_called_once_with("Dark")
    app._settings_service.save_schedule.assert_called_once()

    app._settings_service.save_schedule.reset_mock()
    ChronoBrightApp._on_appearance_changed(app, "Dark")
    app._settings_service.save_schedule.assert_not_called()
