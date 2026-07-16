"""Escalate active decline alerts against the weather forecast.

A field that is already declining and has little rain coming is more likely
genuinely water-stressed than one with rain on the way. When the next-7-day
forecast is dry, the alert's severity is raised one tier and tagged
likely_water_stress. The rain figures are recorded in the evidence either way,
so the reasoning is always visible.
"""

from __future__ import annotations

from typing import Any, Final

from app.alerts.engine import Alert
from app.weather.client import WeatherSummary

# Below this much forecast rain over the next 7 days, a decline is treated as
# probable water stress.
DRY_THRESHOLD_MM: Final = 5.0

_NEXT_SEVERITY: Final[dict[str, str]] = {"low": "medium", "medium": "high", "high": "high"}


def _escalate_severity(severity: str) -> str:
    return _NEXT_SEVERITY.get(severity, severity)


def apply_weather(alert: Alert, weather: WeatherSummary) -> Alert:
    """Return the alert with rain evidence, escalated if the forecast is dry."""
    evidence: dict[str, Any] = {
        **alert.evidence,
        "rain_next_7d_mm": weather.rain_next_7d_mm,
        "rain_past_14d_mm": weather.rain_past_14d_mm,
    }
    severity = alert.severity

    if weather.rain_next_7d_mm < DRY_THRESHOLD_MM:
        severity = _escalate_severity(severity)
        evidence["likely_water_stress"] = True

    return Alert(type=alert.type, zone=alert.zone, severity=severity, evidence=evidence)
