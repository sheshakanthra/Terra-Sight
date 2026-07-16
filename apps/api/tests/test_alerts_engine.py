"""Trend-and-alert engine — Phase 3 acceptance.

Covers alert types, severities, the zero-alert healthy case, zone localization,
the below-median guard, insufficient data, the trend window, and determinism.
"""

from datetime import date, timedelta

import numpy as np
import pytest

from app.alerts.engine import (
    ALERT_FIELD_DECLINE,
    ALERT_ZONE_DECLINE,
    MIN_OBSERVATIONS,
    ObservationPoint,
    _detect_decline,
    detect_alerts,
)

START = date(2026, 6, 1)
STEP_DAYS = 5


def linear(a: float, b: float, n: int) -> list[float]:
    return [float(v) for v in np.linspace(a, b, n)]


def points(
    field_series: list[float],
    zone_series: dict[str, list[float | None]] | None = None,
) -> list[ObservationPoint]:
    pts: list[ObservationPoint] = []
    for i, fm in enumerate(field_series):
        zone_medians: dict[str, float] = {}
        if zone_series:
            for label, series in zone_series.items():
                value = series[i]
                if value is not None:
                    zone_medians[label] = value
        pts.append(
            ObservationPoint(
                date=START + timedelta(days=STEP_DAYS * i),
                field_median=fm,
                zone_medians=zone_medians,
            )
        )
    return pts


class TestHealthyProducesNoAlerts:
    def test_flat_series(self) -> None:
        assert detect_alerts(points([0.7] * 6)) == []

    def test_rising_series(self) -> None:
        assert detect_alerts(points(linear(0.4, 0.8, 6))) == []

    def test_noisy_but_shallow_decline_under_threshold(self) -> None:
        # ~6% drop, below the 10% rule.
        assert detect_alerts(points([0.70, 0.68, 0.71, 0.67, 0.69, 0.66])) == []


class TestFieldDecline:
    def test_a_declining_field_raises_one_field_alert(self) -> None:
        alerts = detect_alerts(points(linear(0.8, 0.5, 5)))
        assert len(alerts) == 1
        assert alerts[0].type == ALERT_FIELD_DECLINE
        assert alerts[0].zone == "field"

    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            (0.70, 0.60, "low"),     # ~14%
            (0.80, 0.60, "medium"),  # 25%
            (0.80, 0.45, "high"),    # ~44%
        ],
    )
    def test_severity_tiers(self, a: float, b: float, expected: str) -> None:
        alerts = detect_alerts(points(linear(a, b, 5)))
        assert len(alerts) == 1
        assert alerts[0].severity == expected


class TestBelowMedianGuard:
    def test_decline_with_current_above_median_does_not_alert(self) -> None:
        # A clear fitted decline, but the last reading ticks back above the
        # series median — easing off a high, not currently stressed.
        dates = [START + timedelta(days=STEP_DAYS * i) for i in range(4)]
        assert _detect_decline(dates, [0.90, 0.70, 0.65, 0.85]) is None

    def test_same_shape_but_current_below_median_does_alert(self) -> None:
        dates = [START + timedelta(days=STEP_DAYS * i) for i in range(4)]
        assert _detect_decline(dates, [0.90, 0.75, 0.70, 0.55]) is not None


class TestInsufficientData:
    def test_below_minimum_observations_never_alerts(self) -> None:
        series = linear(0.8, 0.4, MIN_OBSERVATIONS - 1)
        assert detect_alerts(points(series)) == []

    def test_exactly_minimum_observations_can_alert(self) -> None:
        series = linear(0.8, 0.4, MIN_OBSERVATIONS)
        assert len(detect_alerts(points(series))) == 1


class TestTrendWindow:
    def test_only_the_most_recent_window_is_considered(self) -> None:
        # Old high readings then a flat recent run: no decline within the window.
        series = [0.9, 0.9, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        assert detect_alerts(points(series)) == []

    def test_a_recent_decline_is_caught_despite_older_low_readings(self) -> None:
        series = [0.5, 0.5, 0.90, 0.85, 0.80, 0.75, 0.70, 0.55]
        alerts = detect_alerts(points(series))
        assert any(a.type == ALERT_FIELD_DECLINE for a in alerts)


class TestZoneLocalization:
    def test_one_declining_zone_alerts_while_the_field_stays_flat(self) -> None:
        zones = {
            "NW": linear(0.75, 0.40, 5),
            "C": [0.6] * 5,
            "SE": [0.62] * 5,
        }
        alerts = detect_alerts(points([0.6] * 5, zone_series=zones))
        assert [a.type for a in alerts] == [ALERT_ZONE_DECLINE]
        assert alerts[0].zone == "NW"

    def test_a_zone_present_in_too_few_observations_is_skipped(self) -> None:
        # NW declines, but only appears on 3 of 6 dates (clouded otherwise).
        nw: list[float | None] = [0.8, None, 0.6, None, 0.4, None]
        alerts = detect_alerts(points([0.6] * 6, zone_series={"NW": nw}))
        assert alerts == []


class TestDeterminism:
    def test_same_history_yields_identical_alerts(self) -> None:
        pts = points(linear(0.8, 0.45, 6))
        first = detect_alerts(pts)
        second = detect_alerts(pts)
        assert first == second


class TestEvidence:
    def test_evidence_carries_the_numbers_behind_the_alert(self) -> None:
        alerts = detect_alerts(points(linear(0.80, 0.50, 5)))
        evidence = alerts[0].evidence
        assert evidence["start_ndvi"] == pytest.approx(0.80, abs=0.01)
        assert evidence["end_ndvi"] == pytest.approx(0.50, abs=0.01)
        assert evidence["decline_pct"] == pytest.approx(37.5, abs=0.5)
        assert evidence["window_days"] == STEP_DAYS * 4
        assert evidence["n_observations"] == 5
        assert evidence["current_ndvi"] == pytest.approx(0.50, abs=0.01)
