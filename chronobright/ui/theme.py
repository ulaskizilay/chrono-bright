import customtkinter as ctk

from chronobright import config


def apply_theme(mode: object = None) -> str:
    """Apply appearance mode and color theme. Returns the normalized mode."""
    normalized = config.normalize_appearance(mode if mode is not None else config.APPEARANCE_MODE)
    ctk.set_appearance_mode(normalized)
    ctk.set_default_color_theme(config.COLOR_THEME)
    return normalized
