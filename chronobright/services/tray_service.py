"""System tray icon management via pystray."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from chronobright.i18n import Translator
from chronobright.logger import get_logger

logger = get_logger(__name__)


class TrayService:
    """Create and manage a system tray icon with Show/Hide/Exit menu items."""

    def __init__(
        self,
        on_show_window: Callable[[], None],
        on_hide_window: Callable[[], None],
        on_exit_application: Callable[[], None],
        translate: Callable[..., str] | None = None,
        is_window_visible: Callable[[], bool] | None = None,
    ) -> None:
        self._on_show_window = on_show_window
        self._on_hide_window = on_hide_window
        self._on_exit_application = on_exit_application
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None
        self._window_visible = True
        self._is_window_visible = is_window_visible
        self._translate = translate or Translator().translate
        self._active_period: str | None = None
        self._active_level: int | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Create the tray icon and start it in a daemon thread. No-op if already running."""
        if self._thread and self._thread.is_alive():
            return

        self._icon = pystray.Icon(
            name="ChronoBright",
            title="ChronoBright",
            icon=self._create_icon_image(),
            menu=self._build_menu(),
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        logger.info("Tray icon started.")

    def stop(self) -> None:
        """Stop and remove the tray icon."""
        if self._icon is None:
            return
        self._icon.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._icon = None
        self._thread = None
        logger.info("Tray icon stopped.")

    def _current_visibility(self) -> bool:
        if self._is_window_visible is not None:
            try:
                return bool(self._is_window_visible())
            except Exception:
                pass
        return self._window_visible

    def set_window_visible(self, is_visible: bool) -> None:
        """Mirror visibility state (kept for compatibility; provider wins)."""
        self._window_visible = is_visible
        self._update_menu()

    def set_active_period(self, period: str, level: int) -> None:
        """Update the tray tooltip to reflect the active schedule period."""
        self._active_period = period
        self._active_level = level
        if self._icon is not None:
            with contextlib.suppress(Exception):
                self._icon.title = self._tray_title()

    def _tray_title(self) -> str:
        if self._active_period is not None and self._active_level is not None:
            try:
                return self._translate(
                    "tray_status", period=self._active_period, level=self._active_level
                )
            except Exception:
                pass
        return "ChronoBright"

    def refresh_menu_text(self) -> None:
        """Rebuild menu labels after the application language changes."""
        self._update_menu()
        if self._icon is None:
            return
        self._icon.menu = self._build_menu()
        with contextlib.suppress(Exception):
            self._icon.title = self._tray_title()
        self._update_menu()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                self._translate("tray_show"),
                self._show_window,
                default=True,
                enabled=self._can_show_window,
            ),
            pystray.MenuItem(self._translate("tray_hide"), self._hide_window, enabled=self._can_hide_window),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._translate("tray_exit"), self._exit_application),
        )

    def _show_window(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._on_show_window()

    def _hide_window(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._on_hide_window()

    def _exit_application(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._on_exit_application()

    def _can_show_window(self, item: pystray.MenuItem) -> bool:
        return not self._current_visibility()

    def _can_hide_window(self, item: pystray.MenuItem) -> bool:
        return self._current_visibility()

    def _update_menu(self) -> None:
        if self._icon is None:
            return
        self._icon.update_menu()

    @staticmethod
    def _create_icon_image() -> Image.Image:
        size = 64
        background_color = "#1f2937"
        accent_color = "#f59e0b"
        text_color = "#f8fafc"

        image = Image.new("RGB", (size, size), background_color)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=background_color, outline=accent_color, width=3)
        draw.rectangle((16, 20, 48, 28), fill=accent_color)
        draw.rectangle((16, 36, 38, 44), fill=text_color)
        draw.rectangle((40, 36, 48, 44), fill=accent_color)
        return image
