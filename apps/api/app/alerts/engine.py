"""Pure trend-and-alert engine.

Given a field's recent NDVI observations (whole-field and per-zone medians), it
decides — deterministically — whether a real decline has occurred and emits
alerts carrying the numbers behind the call. No I/O, no LLM.

The rule (Appendix A, Phase 3): a relative NDVI decline of at least 10% over the
trend window **and** a current NDVI below the series' own median. "Its own
median" is applied per series — the whole field is judged against the field's
median, a zone against that zone's median — because zones have different natural
baselines and a drier corner should not alert merely for being itself.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from typing import Final

import numpy as np

# Minimum valid observations before a trend is trustworthy; the window keeps at
# most the most recent WINDOW_MAX (~4-6 passes ≈ 20-30 days).
MIN_OBSERVATIONS: Final = 4
WINDOW_MAX: Final = 6

# Relative decline (fraction) required to alert, and the severity tier cutoffs.
DECLINE_THRESHOLD: Final = 0.10
SEVERITY_MEDIUM_AT: Final = 0.20
SEVERITY_HIGH_AT: Final = 0.35

FIELD_ZONE: Final = "field"
ALERT_FIELD_DECLINE: Final = "field_decline"
ALERT_ZONE_DECLINE: Final = "zone_decline"

# 3x3 grid labels, row-major from the north-west (arrays are north-up).
ZONE_LABELS: Final[tuple[tuple[str, str, str], ...]] = (
    ("NW", "N", "NE"),
    ("W", "C", "E"),
    ("SW", "S", "SE"),
)


def zone_label(row: int, col: int) -> str:
    return ZONE_LABELS[row][col]


@dataclass(frozen=True)
class ObservationPoint:
    """One observation's NDVI medians. Zones absent from `zone_medians` had no
    valid pixels on that date and are simply skipped for that zone's trend."""

    date: date
    field_median: float
    zone_medians: dict[str, float]


@dataclass(frozen=True)
class Alert:
    type: str
    zone: str
    severity: str
    evidence: dict[str, float | int]


@dataclass(frozen=True)
class _Decline:
    fit_start: float
    fit_end: float
    fraction: float


def _linear_endpoints(days: list[float], values: list[float]) -> tuple[float, float]:
    """Fit NDVI against day-offset and return the fitted first/last values.

    A linear fit rather than raw first-vs-last: valid pixel coverage varies
    between dates, so endpoints are noisy; the fit uses every point and resists a
    single bad pass swinging the verdict.
    """
    slope, intercept = np.polyfit(days, values, 1)
    return float(intercept + slope * days[0]), float(intercept + slope * days[-1])


def _severity(fraction: float) -> str:
    if fraction >= SEVERITY_HIGH_AT:
        return "high"
    if fraction >= SEVERITY_MEDIUM_AT:
        return "medium"
    return "low"


def _detect_decline(dates: list[date], values: list[float]) -> _Decline | None:
    """A decline that clears the threshold and is currently below its own median."""
    if len(values) < MIN_OBSERVATIONS:
        return None
    days = [float((d - dates[0]).days) for d in dates]
    if len(set(days)) < 2:
        return None

    fit_start, fit_end = _linear_endpoints(days, values)
    if fit_start <= 0:
        return None

    fraction = (fit_start - fit_end) / fit_start
    if fraction < DECLINE_THRESHOLD:
        return None

    # Only alert if the field is now below its typical level, not merely easing
    # off an unusually high reading.
    if values[-1] >= statistics.median(values):
        return None

    return _Decline(fit_start=fit_start, fit_end=fit_end, fraction=fraction)


def _evidence(decline: _Decline, dates: list[date], values: list[float]) -> dict[str, float | int]:
    return {
        "start_ndvi": round(decline.fit_start, 4),
        "end_ndvi": round(decline.fit_end, 4),
        "current_ndvi": round(values[-1], 4),
        "baseline_median": round(statistics.median(values), 4),
        "decline_pct": round(decline.fraction * 100, 1),
        "window_days": (dates[-1] - dates[0]).days,
        "n_observations": len(values),
    }


def _window(points: list[ObservationPoint]) -> list[ObservationPoint]:
    return sorted(points, key=lambda p: p.date)[-WINDOW_MAX:]


def detect_alerts(points: list[ObservationPoint]) -> list[Alert]:
    """All active alerts for a field, given its observation history.

    Whole-field decline and each declining zone produce distinct alert types
    (field_decline / zone_decline). Deterministic: the same history always yields
    the same alerts, which is what makes refresh idempotent.
    """
    window = _window(points)
    if len(window) < MIN_OBSERVATIONS:
        return []

    alerts: list[Alert] = []
    dates = [p.date for p in window]

    field_values = [p.field_median for p in window]
    field_decline = _detect_decline(dates, field_values)
    if field_decline is not None:
        alerts.append(
            Alert(
                type=ALERT_FIELD_DECLINE,
                zone=FIELD_ZONE,
                severity=_severity(field_decline.fraction),
                evidence=_evidence(field_decline, dates, field_values),
            )
        )

    for row in range(3):
        for col in range(3):
            label = zone_label(row, col)
            zone_dates: list[date] = []
            zone_values: list[float] = []
            for point in window:
                value = point.zone_medians.get(label)
                if value is not None:
                    zone_dates.append(point.date)
                    zone_values.append(value)

            zone_decline = _detect_decline(zone_dates, zone_values)
            if zone_decline is not None:
                alerts.append(
                    Alert(
                        type=ALERT_ZONE_DECLINE,
                        zone=label,
                        severity=_severity(zone_decline.fraction),
                        evidence=_evidence(zone_decline, zone_dates, zone_values),
                    )
                )

    return alerts
