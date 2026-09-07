"""Windows autostart via HKCU Run registry key."""

from __future__ import annotations

import sys

from chronobright.logger import get_logger

logger = get_logger(__name__)

APP_REG_NAME = "ChronoBright"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_command() -> str:
    exe = sys.executable.replace('"', "")
    if exe.lower().endswith("python.exe") or exe.lower().endswith("pythonw.exe"):
        return f'"{exe}" -m chronobright --minimized'
    return f'"{exe}" --minimized'


class AutostartService:
    """Enable/disable launch at Windows login for the current user."""

    def __init__(self, app_name: str = APP_REG_NAME) -> None:
        self._app_name = app_name

    def is_enabled(self) -> bool:
        try:
            import winreg
        except ImportError:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, self._app_name)
                return bool(value)
        except OSError:
            return False

    def enable(self) -> None:
        try:
            import winreg
        except ImportError as exc:
            raise RuntimeError("Autostart is only supported on Windows.") from exc
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.SetValueEx(key, self._app_name, 0, winreg.REG_SZ, _startup_command())
            logger.info("Autostart enabled.")
        except OSError as exc:
            raise RuntimeError(f"Could not enable autostart: {exc}") from exc

    def disable(self) -> None:
        try:
            import winreg
        except ImportError as exc:
            raise RuntimeError("Autostart is only supported on Windows.") from exc
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self._app_name)
            logger.info("Autostart disabled.")
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(f"Could not disable autostart: {exc}") from exc

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.enable()
        else:
            self.disable()
