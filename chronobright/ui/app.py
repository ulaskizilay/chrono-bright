"""Main application window for ChronoBright."""

from __future__ import annotations

import queue
from collections.abc import Callable

import customtkinter as ctk

from chronobright import config
from chronobright.i18n import SUPPORTED_LANGUAGES, Translator
from chronobright.logger import get_logger
from chronobright.models import BrightnessScheduleConfig
from chronobright.services.autostart_service import AutostartService
from chronobright.services.brightness_service import BrightnessService
from chronobright.services.schedule_service import ScheduleService
from chronobright.services.settings_service import SettingsLoadResult, SettingsService
from chronobright.services.tray_service import TrayService
from chronobright.ui.theme import apply_theme

logger = get_logger(__name__)


class ChronoBrightApp(ctk.CTk):  # type: ignore[misc]
    """Top-level application window.

    Wires up the service layer and builds the UI on initialisation.
    The schedule and tray icon start immediately; the window can be hidden
    to the system tray without stopping background services.
    """

    def __init__(self) -> None:
        # Load settings BEFORE Tk init so the saved theme applies immediately.
        self._settings_service = SettingsService()
        loaded_settings = self._settings_service.load_schedule()
        self._appearance = loaded_settings.appearance
        apply_theme(self._appearance)
        super().__init__()

        self.title(config.APP_TITLE)
        self.geometry(config.WINDOW_SIZE)
        self.minsize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resizable(True, False)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._brightness_service = BrightnessService()
        self._startup_brightness = self._brightness_service.get_all_brightness()
        self._autostart_service = AutostartService()
        self._current_schedule_config = loaded_settings.config
        self._translator = Translator(loaded_settings.language)
        self._schedule_service = ScheduleService(on_brightness_change=self._apply_brightness)
        self._tray_service = TrayService(
            on_show_window=self._show_window_from_tray,
            on_hide_window=self._hide_window_from_tray,
            on_exit_application=self._exit_from_tray,
            translate=self._translate,
            is_window_visible=self._is_window_visible_for_tray,
        )
        self._is_exiting = False
        self._window_in_tray = False

        self._build_layout()
        self._load_saved_schedule(loaded_settings)
        self._fit_window_to_content()
        self.after(50, self._drain_ui_queue)
        self._schedule_service.start()
        self._tray_service.start()

    def _fit_window_to_content(self) -> None:
        """Size the window height to the content so no dead space remains.

        Width stays at the configured size; height shrinks/grows to the
        measured content. minsize tracks the fitted height so the window can
        never be squeezed shorter than its content (no clipping), and vertical
        resizing is disabled so users cannot create dead space either.
        """
        try:
            self.update_idletasks()
            req_h = int(self.winfo_reqheight())
        except Exception as exc:
            logger.debug("Could not fit window to content: %s", exc)
            return
        try:
            width = self.geometry().split("+", 1)[0].split("x", 1)[0]
            width_px = max(int(width), config.WINDOW_MIN_WIDTH)
        except Exception:
            width_px = max(700, config.WINDOW_MIN_WIDTH)
        height_px = max(req_h, 400)
        try:
            self.geometry(f"{width_px}x{height_px}")
            self.minsize(config.WINDOW_MIN_WIDTH, height_px)
        except Exception as exc:
            logger.debug("Could not apply fitted window size: %s", exc)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.grid_columnconfigure((0, 1), weight=1, uniform="cols")
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)
        self.grid_rowconfigure(4, weight=0)
        self.grid_rowconfigure(5, weight=0)

        # Top bar: title block left, language + theme selectors right.
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 2))
        top_bar.grid_columnconfigure(0, weight=1)
        top_bar.grid_columnconfigure(1, weight=0)

        title_block = ctk.CTkFrame(top_bar, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")
        self._header_label = ctk.CTkLabel(
            title_block,
            text=self._translate("header"),
            font=ctk.CTkFont(size=19, weight="bold"),
            anchor="w",
            justify="left",
        )
        self._header_label.grid(row=0, column=0, sticky="w", padx=(4, 0))
        self._subtitle_label = ctk.CTkLabel(
            title_block,
            text=self._translate("subtitle"),
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w",
            justify="left",
        )
        self._subtitle_label.grid(row=1, column=0, sticky="w", padx=(4, 0), pady=(0, 2))

        controls = ctk.CTkFrame(top_bar, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="e")
        controls.grid_columnconfigure((0, 1), weight=0)

        lang_frame = ctk.CTkFrame(controls, fg_color="transparent")
        lang_frame.grid(row=0, column=0, padx=(0, 12), sticky="n")
        self._language_label = ctk.CTkLabel(lang_frame, text=self._translate("language"))
        self._language_label.grid(row=0, column=0, sticky="e")
        self._language_selector = ctk.CTkOptionMenu(
            lang_frame,
            values=list(SUPPORTED_LANGUAGES.values()),
            command=self._on_language_changed,
            width=110,
        )
        self._language_selector.set(SUPPORTED_LANGUAGES[self._translator.language])
        self._language_selector.grid(row=1, column=0, sticky="e", pady=(2, 0))

        theme_frame = ctk.CTkFrame(controls, fg_color="transparent")
        theme_frame.grid(row=0, column=1, sticky="n")
        self._theme_label = ctk.CTkLabel(theme_frame, text=self._translate("theme"))
        self._theme_label.grid(row=0, column=0, sticky="e")
        self._theme_selector = ctk.CTkOptionMenu(
            theme_frame,
            values=list(config.APPEARANCE_OPTIONS),
            command=self._on_appearance_changed,
            width=110,
        )
        self._theme_selector.set(self._appearance)
        self._theme_selector.grid(row=1, column=0, sticky="e", pady=(2, 0))

        self._build_hero_card()
        self._build_morning_panel()
        self._build_evening_panel()

        self._btn_apply = ctk.CTkButton(
            self,
            text=self._translate("save_apply"),
            command=self._on_apply_clicked,
            height=36,
            corner_radius=10,
            font=ctk.CTkFont(weight="bold"),
        )
        self._btn_apply.grid(row=3, column=0, padx=(16, 8), pady=10, sticky="ew")

        self._btn_exit = ctk.CTkButton(
            self,
            text=self._translate("exit"),
            fg_color="#b91c1c",
            hover_color="#991b1b",
            height=36,
            corner_radius=10,
            font=ctk.CTkFont(weight="bold"),
            command=self.exit_application,
        )
        self._btn_exit.grid(row=3, column=1, padx=(8, 16), pady=10, sticky="ew")

        self._autostart_var = ctk.BooleanVar(value=self._autostart_service.is_enabled())
        self._chk_autostart = ctk.CTkCheckBox(
            self,
            text=self._translate("autostart"),
            variable=self._autostart_var,
            command=self._on_autostart_toggled,
        )
        self._chk_autostart.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 5), sticky="w")

        self._lbl_status = ctk.CTkLabel(
            self,
            text="Status: Idle — configure and press Apply",
            text_color="gray",
            wraplength=620,
            justify="center",
        )
        self._lbl_status.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 14), sticky="ew")
        self._hero_period_key: str | None = None
        self._hero_level_value: int | None = None
        self._set_status("idle", "gray")

    def _build_hero_card(self) -> None:
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, columnspan=2, padx=16, pady=(6, 2), sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)
        self._hero_card = card

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=16, pady=12)
        self._hero_kicker = ctk.CTkLabel(
            left, text=self._translate("now"), font=ctk.CTkFont(size=11, weight="bold"), text_color="gray"
        )
        self._hero_kicker.grid(row=0, column=0, sticky="w")
        self._hero_period = ctk.CTkLabel(left, text="—", font=ctk.CTkFont(size=22, weight="bold"))
        self._hero_period.grid(row=1, column=0, sticky="w")
        self._hero_level_label = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=14), text_color="gray"
        )
        self._hero_level_label.grid(row=2, column=0, sticky="w")

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=1, sticky="ew", padx=16, pady=12)
        right.grid_columnconfigure(0, weight=1)
        self._hero_bar = ctk.CTkProgressBar(right, height=12, corner_radius=6)
        self._hero_bar.set(0.0)
        self._hero_bar.grid(row=0, column=0, sticky="ew", pady=(8, 6))
        self._hero_schedule = ctk.CTkLabel(
            right, text="", font=ctk.CTkFont(size=12), text_color="gray", wraplength=300, justify="right"
        )
        self._hero_schedule.grid(row=1, column=0, sticky="e")

    def _build_morning_panel(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=12, border_width=2)
        frame.grid(row=2, column=0, padx=(16, 8), pady=4, sticky="new")
        frame.grid_columnconfigure(0, weight=1)
        self._morning_frame = frame

        self._morning_heading = ctk.CTkLabel(
            frame,
            text="\u2600 " + self._translate("morning_settings"),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config.MORNING_ACCENT,
        )
        self._morning_heading.grid(row=0, column=0, padx=10, pady=(8, 0))

        self._morning_time_caption = ctk.CTkLabel(
            frame, text=self._translate("time_caption"), font=ctk.CTkFont(size=11), text_color="gray"
        )
        self._morning_time_caption.grid(row=1, column=0, pady=0)

        self._entry_morning_time = ctk.CTkEntry(
            frame,
            placeholder_text=config.DEFAULT_MORNING_TIME,
            width=120,
            justify="center",
            font=ctk.CTkFont(size=14),
        )
        self._entry_morning_time.insert(0, config.DEFAULT_MORNING_TIME)
        self._entry_morning_time.grid(row=2, column=0, padx=20, pady=(4, 2))

        self._slider_morning = ctk.CTkSlider(
            frame,
            from_=config.MIN_BRIGHTNESS,
            to=config.MAX_BRIGHTNESS,
            number_of_steps=config.MAX_BRIGHTNESS - config.MIN_BRIGHTNESS,
            button_color=config.MORNING_ACCENT,
            progress_color=config.MORNING_ACCENT,
        )
        self._slider_morning.set(config.DEFAULT_MORNING_BRIGHTNESS)
        self._slider_morning.grid(row=3, column=0, padx=20, pady=2, sticky="ew")
        self._slider_morning.configure(command=self._on_morning_slider_moved)

        self._lbl_morning_value = ctk.CTkLabel(
            frame,
            text=self._translate("brightness", level=config.DEFAULT_MORNING_BRIGHTNESS),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.MORNING_ACCENT,
        )
        self._lbl_morning_value.grid(row=4, column=0, pady=(0, 6))

    def _build_evening_panel(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=12, border_width=2)
        frame.grid(row=2, column=1, padx=(8, 16), pady=4, sticky="new")
        frame.grid_columnconfigure(0, weight=1)
        self._evening_frame = frame

        self._evening_heading = ctk.CTkLabel(
            frame,
            text="\u263e " + self._translate("evening_settings"),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config.EVENING_ACCENT,
        )
        self._evening_heading.grid(row=0, column=0, padx=10, pady=(8, 0))

        self._evening_time_caption = ctk.CTkLabel(
            frame, text=self._translate("time_caption"), font=ctk.CTkFont(size=11), text_color="gray"
        )
        self._evening_time_caption.grid(row=1, column=0, pady=0)

        self._entry_evening_time = ctk.CTkEntry(
            frame,
            placeholder_text=config.DEFAULT_EVENING_TIME,
            width=120,
            justify="center",
            font=ctk.CTkFont(size=14),
        )
        self._entry_evening_time.insert(0, config.DEFAULT_EVENING_TIME)
        self._entry_evening_time.grid(row=2, column=0, padx=20, pady=(4, 2))

        self._slider_evening = ctk.CTkSlider(
            frame,
            from_=config.MIN_BRIGHTNESS,
            to=config.MAX_BRIGHTNESS,
            number_of_steps=config.MAX_BRIGHTNESS - config.MIN_BRIGHTNESS,
            button_color=config.EVENING_ACCENT,
            progress_color=config.EVENING_ACCENT,
        )
        self._slider_evening.set(config.DEFAULT_EVENING_BRIGHTNESS)
        self._slider_evening.grid(row=3, column=0, padx=20, pady=2, sticky="ew")
        self._slider_evening.configure(command=self._on_evening_slider_moved)

        self._lbl_evening_value = ctk.CTkLabel(
            frame,
            text=self._translate("brightness", level=config.DEFAULT_EVENING_BRIGHTNESS),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.EVENING_ACCENT,
        )
        self._lbl_evening_value.grid(row=4, column=0, pady=(0, 6))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_morning_slider_moved(self, value: float) -> None:
        self._lbl_morning_value.configure(text=self._translate("brightness", level=int(value)))

    def _on_evening_slider_moved(self, value: float) -> None:
        self._lbl_evening_value.configure(text=self._translate("brightness", level=int(value)))

    def _on_apply_clicked(self) -> None:
        # Save first, then apply atomically. If save_schedule raises OSError on disk
        # failure, apply_schedule is never called and the in-memory scheduler is left
        # untouched (yesterday's schedule keeps running). ValueError here can only come
        # from _read_form_config validating an empty/invalid entry.
        try:
            schedule_config = self._read_form_config()
            self._settings_service.save_schedule(
                schedule_config, self._translator.language, self._appearance
            )
            self._schedule_service.apply_schedule(schedule_config)
            self._current_schedule_config = schedule_config
            self._update_hero_schedule()
            self._set_status("schedule_saved", "green")
        except ValueError as exc:
            logger.warning("Invalid schedule input: %s", exc)
            self._set_status("invalid_input", "red")
        except OSError as exc:
            logger.error("Failed to save config: %s", exc)
            self._set_status("save_error", "red")

    def _on_language_changed(self, display_name: str) -> None:
        """Switch visible text without rebuilding widgets or restarting services."""
        language = next(
            (code for code, name in SUPPORTED_LANGUAGES.items() if name == display_name),
            None,
        )
        if language is None:
            logger.warning("Unknown language display name: %r", display_name)
            return
        if language == self._translator.language:
            return
        self._translator.set_language(language)
        try:
            self._settings_service.save_schedule(
                self._current_schedule_config, language, self._appearance
            )
        except OSError as exc:
            logger.error("Failed to save language preference: %s", exc)
        self._refresh_translated_widgets()

    def _on_appearance_changed(self, mode: str) -> None:
        """Switch CustomTkinter appearance mode and persist the choice."""
        normalized = config.normalize_appearance(mode)
        if normalized == self._appearance:
            return
        self._appearance = normalized
        ctk.set_appearance_mode(normalized)
        try:
            self._settings_service.save_schedule(
                self._current_schedule_config, self._translator.language, normalized
            )
        except OSError as exc:
            logger.error("Failed to save appearance preference: %s", exc)

    def _on_autostart_toggled(self) -> None:
        enabled = bool(self._autostart_var.get())
        try:
            self._autostart_service.set_enabled(enabled)
        except RuntimeError as exc:
            logger.error("%s", exc)
            # Revert the checkbox so UI reflects reality.
            self._autostart_var.set(not enabled)
            self._set_status("autostart_error", "red")

    def _on_window_close(self) -> None:
        self.hide_window_to_tray()

    # ------------------------------------------------------------------
    # Thread-safe UI queue: background threads NEVER touch Tk directly.
    # They enqueue callables; the main loop drains them via after().
    # ------------------------------------------------------------------

    def _is_window_visible_for_tray(self) -> bool:
        """Single source of truth for tray menu state (owned by the App)."""
        return not self._window_in_tray and not self._is_exiting

    def _drain_ui_queue(self) -> None:
        if self._is_exiting:
            return
        try:
            while True:
                try:
                    func = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    func()
                except Exception:
                    logger.exception("UI queue task failed")
                finally:
                    self._ui_queue.task_done()
        finally:
            if not self._is_exiting:
                try:
                    self.after(50, self._drain_ui_queue)
                except Exception as exc:
                    logger.debug("Could not reschedule UI drain: %s", exc)

    # ------------------------------------------------------------------
    # Public interface called by the schedule or tray service
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_period_key(period_name: object) -> str:
        """Map scheduler period labels to translation keys robustly."""
        if isinstance(period_name, str):
            token = period_name.strip().split()[0].lower() if period_name.strip() else ""
            if token in ("morning", "evening"):
                return token
            lowered = period_name.strip().lower()
            if lowered in ("morning", "evening"):
                return lowered
        logger.warning("Unknown period name %r, defaulting to 'morning'", period_name)
        return "morning"

    def _run_on_ui_thread(self, func: Callable[[], None]) -> None:
        """Enqueue *func* for the Tk main loop. Never touches Tk directly.

        Safe to call from scheduler/tray threads. The main loop executes the
        callable via :meth:`_drain_ui_queue`.
        """
        if self._is_exiting:
            return
        self._ui_queue.put(func)

    def _apply_brightness(self, level: int, period_name: str) -> None:
        """Set the display brightness (any thread) and queue the status update."""
        try:
            target = int(level)
        except (TypeError, ValueError):
            logger.error("Invalid brightness level from scheduler: %r", level)
            self._update_status_safe("brightness_error", "red")
            return
        # Clamp to the safe UI minimum so a corrupt config can never black out
        # the screen via the scheduler path.
        if target < config.MIN_BRIGHTNESS:
            logger.warning(
                "Scheduler requested %d%%, clamping to minimum %d%%.",
                target,
                config.MIN_BRIGHTNESS,
            )
            target = config.MIN_BRIGHTNESS
        if target > config.MAX_BRIGHTNESS:
            target = config.MAX_BRIGHTNESS
        logger.info("Applying %s brightness: %d%%", period_name, target)

        try:
            self._brightness_service.set_brightness(target)
            period_key = self._normalize_period_key(period_name)
            self._run_on_ui_thread(lambda: self._show_active_state(period_key, target))
        except (RuntimeError, ValueError) as exc:
            logger.error("%s", exc)
            self._update_status_safe("brightness_error", "red")

    def _show_active_state(self, period_key: str, level: int) -> None:
        """Refresh status bar, hero card, panel highlight and tray (main thread)."""
        self._set_status("brightness_applied", "blue", level=level, period_key=period_key)
        self._update_hero(period_key, level)
        self._highlight_active_period(period_key)
        self._update_tray_period(period_key, level)

    def _update_hero(self, period_key: str, level: int) -> None:
        """Update the hero card with the active period and brightness."""
        self._hero_period_key = period_key
        self._hero_level_value = level
        accent = config.MORNING_ACCENT if period_key == "morning" else config.EVENING_ACCENT
        self._hero_period.configure(text=self._translate(period_key), text_color=accent)
        self._hero_level_label.configure(text=f"{level}%")
        self._hero_bar.set(max(0.0, min(1.0, level / 100.0)))
        self._hero_bar.configure(progress_color=accent)
        self._update_hero_schedule()

    def _update_hero_schedule(self) -> None:
        """Refresh the hero schedule summary line from the current form values."""
        cfg = self._current_schedule_config
        self._hero_schedule.configure(
            text=self._translate(
                "schedule_summary",
                morning=self._translate("morning"),
                mtime=cfg.morning_time,
                mlevel=cfg.morning_brightness,
                evening=self._translate("evening"),
                etime=cfg.evening_time,
                elevel=cfg.evening_brightness,
            )
        )

    def _highlight_active_period(self, period_key: str) -> None:
        """Outline the active schedule panel with its accent color."""
        if period_key == "morning":
            self._morning_frame.configure(border_width=2, border_color=config.MORNING_ACCENT)
            self._evening_frame.configure(border_width=0)
        else:
            self._morning_frame.configure(border_width=0)
            self._evening_frame.configure(border_width=2, border_color=config.EVENING_ACCENT)

    def hide_window_to_tray(self) -> None:
        """Withdraw the window without stopping background services."""
        if self._is_exiting or self._window_in_tray:
            return

        self.withdraw()
        self._window_in_tray = True
        self._tray_service.refresh_menu_text()
        logger.info("Window hidden to tray.")

    def show_window(self) -> None:
        """Restore the window from the system tray."""
        if self._is_exiting:
            return

        self.deiconify()
        self.lift()
        self.focus_force()
        self._window_in_tray = False
        self._tray_service.refresh_menu_text()
        logger.info("Window restored from tray.")

    def exit_application(self) -> None:
        """Shut down all services, restore startup brightness, and destroy the window."""
        if self._is_exiting:
            return

        self._is_exiting = True
        logger.info("Shutting down application.")
        self._tray_service.stop()
        self._schedule_service.stop()
        self._restore_startup_brightness()
        self.destroy()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _show_window_from_tray(self) -> None:
        self._run_on_ui_thread(self.show_window)

    def _hide_window_from_tray(self) -> None:
        self._run_on_ui_thread(self.hide_window_to_tray)

    def _exit_from_tray(self) -> None:
        self._run_on_ui_thread(self.exit_application)

    def _load_saved_schedule(self, result: SettingsLoadResult | None = None) -> None:
        if result is None:
            result = self._settings_service.load_schedule()
        self._populate_form(result.config)

        # Always activate a schedule so the background thread is never idle:
        # saved config, or defaults when the file is missing/corrupt.
        try:
            self._schedule_service.apply_schedule(result.config)
        except ValueError as exc:
            logger.error("Default schedule invalid, scheduler left idle: %s", exc)
            self._set_status("corrupt_config", "red")
            return

        if result.source == "saved":
            self._set_status("schedule_loaded", "green")
            return

        if result.source == "fallback":
            self._set_status("corrupt_config", "red")
            return

        self._set_status("missing_config", "gray")

    def _populate_form(self, schedule_config: BrightnessScheduleConfig) -> None:
        self._current_schedule_config = schedule_config
        self._entry_morning_time.delete(0, "end")
        self._entry_morning_time.insert(0, schedule_config.morning_time)
        self._slider_morning.set(schedule_config.morning_brightness)
        self._on_morning_slider_moved(schedule_config.morning_brightness)

        self._entry_evening_time.delete(0, "end")
        self._entry_evening_time.insert(0, schedule_config.evening_time)
        self._slider_evening.set(schedule_config.evening_brightness)
        self._on_evening_slider_moved(schedule_config.evening_brightness)
        self._update_hero_schedule()

    def _read_form_config(self) -> BrightnessScheduleConfig:
        morning_level = int(float(self._slider_morning.get()))
        evening_level = int(float(self._slider_evening.get()))
        for level in (morning_level, evening_level):
            if level < config.MIN_BRIGHTNESS:
                raise ValueError(
                    f"Brightness must be at least {config.MIN_BRIGHTNESS}% "
                    f"to avoid a black screen: {level}"
                )
        cfg = BrightnessScheduleConfig(
            morning_time=self._entry_morning_time.get(),
            morning_brightness=morning_level,
            evening_time=self._entry_evening_time.get(),
            evening_brightness=evening_level,
        )
        cfg.validate()
        return cfg

    def _update_tray_period(self, period_key: str, level: int) -> None:
        self._tray_service.set_active_period(period_key, level)

    def _update_status_safe(self, key: str, color: str, **values: object) -> None:
        def _apply() -> None:
            self._set_status(key, color, **values)

        self._run_on_ui_thread(_apply)

    def _set_status(self, key: str, color: str, **values: object) -> None:
        self._status_key = key
        self._status_values = values
        self._status_color = color
        message = self._format_status(key, values)
        self._lbl_status.configure(text=self._translate("status", message=message), text_color=color)

    def _translate(self, key: str, **values: object) -> str:
        return self._translator.translate(key, **values)

    def _format_status(self, key: str, values: dict[str, object]) -> str:
        if not self._translator.has_key(key):
            return key

        translated_values = dict(values)
        period_key = translated_values.pop("period_key", None)
        if isinstance(period_key, str):
            translated_values["period"] = self._translate(period_key)
        return self._translate(key, **translated_values)

    def _refresh_translated_widgets(self) -> None:
        """Update static labels and the status prefix for the selected language."""
        self.title(self._translate("window_title"))
        self._header_label.configure(text=self._translate("header"))
        self._subtitle_label.configure(text=self._translate("subtitle"))
        self._language_label.configure(text=self._translate("language"))
        self._theme_label.configure(text=self._translate("theme"))
        self._hero_kicker.configure(text=self._translate("now"))
        self._morning_heading.configure(text="\u2600 " + self._translate("morning_settings"))
        self._evening_heading.configure(text="\u263e " + self._translate("evening_settings"))
        self._morning_time_caption.configure(text=self._translate("time_caption"))
        self._evening_time_caption.configure(text=self._translate("time_caption"))
        self._btn_apply.configure(text=self._translate("save_apply"))
        self._btn_exit.configure(text=self._translate("exit"))
        self._chk_autostart.configure(text=self._translate("autostart"))
        self._tray_service.refresh_menu_text()
        self._on_morning_slider_moved(self._slider_morning.get())
        self._on_evening_slider_moved(self._slider_evening.get())
        if self._hero_period_key is not None and self._hero_level_value is not None:
            self._update_hero(self._hero_period_key, self._hero_level_value)
        else:
            self._update_hero_schedule()
        self._set_status(self._status_key, self._status_color, **self._status_values)

    def _restore_startup_brightness(self) -> None:
        if self._startup_brightness is None:
            logger.warning("Skipping brightness restore — initial brightness could not be read.")
            return

        restored = 0
        if len(self._startup_brightness) == 1:
            try:
                self._brightness_service.set_brightness(self._startup_brightness[0])
                restored = 1
            except (RuntimeError, ValueError) as exc:
                logger.error("Failed to restore startup brightness: %s", exc)
        else:
            for index, level in enumerate(self._startup_brightness):
                try:
                    self._brightness_service.set_brightness(level, display=index)
                    restored += 1
                except (RuntimeError, ValueError) as exc:
                    # Best-effort: one failing display must not block the rest.
                    logger.error(
                        "Failed to restore brightness on display %d: %s", index, exc
                    )
        if restored:
            logger.info(
                "Restored startup brightness for %d/%d display(s).",
                restored,
                len(self._startup_brightness),
            )
