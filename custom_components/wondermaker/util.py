"""Kleine Hilfsfunktionen."""

from __future__ import annotations

from typing import Any


def format_duration(seconds: float | None) -> str | None:
    """46 min / 1 h 12 min."""
    if seconds is None:
        return None
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def get_status(data: dict[str, Any] | None, obj: str, key: str, default: Any = None) -> Any:
    """Wert aus dem Klipper-Status lesen."""
    if not data:
        return default
    value = data.get("status", {}).get(obj, {}).get(key, default)
    return default if value is None else value


def interval_option(options: Any, enabled_key: str, interval_key: str, default: int) -> int:
    """Intervall in Sekunden; 0 = aus.

    Aus ist es, wenn der Schalter aus ist oder – bei Einstellungen aus älteren
    Versionen ohne Schalter – das Intervall auf 0 gesetzt war.
    """
    interval = int(options.get(interval_key, default))
    enabled = options.get(enabled_key, interval != 0)
    return interval if enabled and interval > 0 else 0
