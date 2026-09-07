"""Shared time parsing and normalization helpers."""

from __future__ import annotations

from datetime import datetime
from datetime import time as dt_time


def normalize_time_string(value: str) -> str:
    """Parse flexible clock input (e.g. ``8:0``, ``08:00``) and return ``HH:MM``."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid time format: {value}. Use H:MM or HH:MM.")

    stripped = value.strip()
    if not stripped or ":" not in stripped:
        raise ValueError(f"Invalid time format: {value}. Use H:MM or HH:MM.")

    parts = stripped.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid time format: {value}. Use H:MM or HH:MM.")

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"Invalid time format: {value}. Use H:MM or HH:MM.") from exc

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time format: {value}. Use H:MM or HH:MM.")

    return f"{hour:02d}:{minute:02d}"


def parse_clock(value: str) -> dt_time:
    """Return a :class:`datetime.time` for a flexible or normalized clock string."""
    return datetime.strptime(normalize_time_string(value), "%H:%M").time()


def is_morning_period_active(morning_time: str, evening_time: str, now: dt_time) -> bool:
    """Return whether the morning schedule period is active at *now*."""
    morning = parse_clock(morning_time)
    evening = parse_clock(evening_time)

    if morning < evening:
        return morning <= now < evening

    return not (evening <= now < morning)


def seconds_until_next_change(morning_time: str, evening_time: str, now: datetime) -> float:
    """Return seconds from *now* until the next period boundary.

    Used for adaptive sleeping so the background thread does not wake every
    second when the next transition is hours away. Always returns at least 1
    second and at most 15 minutes (to survive manual clock changes).
    """
    from datetime import timedelta

    morning = parse_clock(morning_time)
    evening = parse_clock(evening_time)
    today = now.date()
    deltas: list[float] = []
    for boundary in (morning, evening):
        candidate = datetime.combine(today, boundary)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        deltas.append((candidate - now).total_seconds())
    if not deltas:
        return 60.0
    return max(1.0, min(min(deltas), 15 * 60.0))
