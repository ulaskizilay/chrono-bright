"""Small, dependency-free translation layer for user-facing application text."""

from __future__ import annotations

from typing import Final, Literal

LanguageCode = Literal["en", "tr"]

DEFAULT_LANGUAGE: Final[LanguageCode] = "en"
SUPPORTED_LANGUAGES: Final[dict[LanguageCode, str]] = {
    "en": "English",
    "tr": "Türkçe",
}

_TRANSLATIONS: Final[dict[LanguageCode, dict[str, str]]] = {
    "en": {
        "window_title": "ChronoBright",
        "header": "Display Brightness Scheduler",
        "subtitle": "Automatic brightness, day and night",
        "language": "Language",
        "theme": "Theme",
        "now": "NOW",
        "time_caption": "Time",
        "morning_settings": "Morning Settings",
        "evening_settings": "Evening Settings",
        "brightness": "Brightness: {level}%",
        "save_apply": "Save & Apply Schedule",
        "exit": "Exit Application",
        "status": "Status: {message}",
        "idle": "Idle — configure and press Apply",
        "invalid_input": "Invalid schedule input",
        "save_error": "Could not save settings. Check the log for details.",
        "brightness_error": "Could not change brightness. Check the log for details.",
        "schedule_saved": "Schedule saved and active",
        "schedule_loaded": "Saved schedule loaded and active",
        "corrupt_config": "Invalid settings detected — defaults loaded",
        "missing_config": "No saved schedule — configure and press Apply",
        "brightness_applied": "Set to {level}% ({period})",
        "morning": "Morning",
        "evening": "Evening",
        "immediate": "immediate",
        "tray_show": "Show Window",
        "tray_hide": "Hide Window",
        "tray_exit": "Exit Application",
        "autostart": "Start with Windows",
        "autostart_error": "Could not change autostart setting.",
        "tray_status": "ChronoBright — {period} {level}%",
        "schedule_summary": "{morning} {mtime} → {mlevel}%  ·  {evening} {etime} → {elevel}%",
    },
    "tr": {
        "window_title": "ChronoBright",
        "header": "Ekran Parlaklığı Zamanlayıcısı",
        "subtitle": "Otomatik parlaklık, gece ve gündüz",
        "language": "Dil",
        "theme": "Tema",
        "now": "ŞİMDİ",
        "time_caption": "Saat",
        "morning_settings": "Sabah Ayarları",
        "evening_settings": "Akşam Ayarları",
        "brightness": "Parlaklık: %{level}",
        "save_apply": "Kaydet ve Programı Uygula",
        "exit": "Uygulamadan Çık",
        "status": "Durum: {message}",
        "idle": "Boşta — ayarları yapıp Uygula'ya basın",
        "invalid_input": "Geçersiz program ayarı",
        "save_error": "Ayarlar kaydedilemedi. Ayrıntılar için günlüğü kontrol edin.",
        "brightness_error": "Parlaklık değiştirilemedi. Ayrıntılar için günlüğü kontrol edin.",
        "schedule_saved": "Program kaydedildi ve etkinleştirildi",
        "schedule_loaded": "Kayıtlı program yüklendi ve etkinleştirildi",
        "corrupt_config": "Geçersiz ayarlar algılandı — varsayılanlar yüklendi",
        "missing_config": "Kayıtlı program yok — ayarları yapıp Uygula'ya basın",
        "brightness_applied": "%{level} olarak ayarlandı ({period})",
        "morning": "Sabah",
        "evening": "Akşam",
        "immediate": "hemen",
        "tray_show": "Pencereyi Göster",
        "tray_hide": "Pencereyi Gizle",
        "tray_exit": "Uygulamadan Çık",
        "autostart": "Windows ile başlat",
        "autostart_error": "Otomatik başlatma ayarı değiştirilemedi.",
        "tray_status": "ChronoBright — {period} %{level}",
        "schedule_summary": "{morning} {mtime} → %{mlevel}  ·  {evening} {etime} → %{elevel}",
    },
}


def normalize_language(value: object) -> LanguageCode:
    """Return a supported language code, defaulting safely to English."""
    if isinstance(value, str) and value in SUPPORTED_LANGUAGES:
        return value
    return DEFAULT_LANGUAGE


class Translator:
    """Translate application text without mutable process-wide language state."""

    def __init__(self, language: object = DEFAULT_LANGUAGE) -> None:
        self._language = normalize_language(language)

    @property
    def language(self) -> LanguageCode:
        return self._language

    def set_language(self, language: object) -> None:
        self._language = normalize_language(language)

    def has_key(self, key: str) -> bool:
        """Return whether *key* is a known translation key."""
        return key in _TRANSLATIONS[DEFAULT_LANGUAGE]

    def translate(self, key: str, /, **values: object) -> str:
        """Return the current-language string for *key*, interpolating *values*."""
        template = _TRANSLATIONS[self._language].get(key)
        if template is None:
            template = _TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
        return template.format(**values)
