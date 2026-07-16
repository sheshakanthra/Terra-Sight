"""Weather parsing, the dry-forecast escalation, and the 6h cache."""

import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest

from app.alerts.engine import Alert
from app.weather import client as weather_client
from app.weather.client import CACHE_TTL, WeatherError, WeatherSummary, fetch_weather, parse_daily
from app.weather.escalation import DRY_THRESHOLD_MM, apply_weather


def _daily(start: date, values: list[float | None]) -> dict:
    times = [(start + timedelta(days=i)).isoformat() for i in range(len(values))]
    return {"time": times, "precipitation_sum": values}


class TestParseDaily:
    def test_splits_past_and_next_windows(self) -> None:
        today = date(2026, 7, 16)
        start = today - timedelta(days=14)
        # 14 past days of 1mm, 7 forecast days of 2mm.
        values: list[float | None] = [1.0] * 14 + [2.0] * 7
        summary = parse_daily(_daily(start, values), today)
        assert summary.rain_past_14d_mm == pytest.approx(14.0)
        assert summary.rain_next_7d_mm == pytest.approx(14.0)

    def test_null_precipitation_counts_as_zero(self) -> None:
        today = date(2026, 7, 16)
        start = today
        summary = parse_daily(_daily(start, [None, 3.0, None, 1.0, 0.0, 0.0, 0.0]), today)
        assert summary.rain_next_7d_mm == pytest.approx(4.0)

    def test_mismatched_arrays_raise(self) -> None:
        with pytest.raises(WeatherError):
            parse_daily({"time": ["2026-07-16"], "precipitation_sum": []}, date(2026, 7, 16))

    def test_missing_keys_raise(self) -> None:
        with pytest.raises(WeatherError):
            parse_daily({}, date(2026, 7, 16))


def _alert(severity: str) -> Alert:
    return Alert(type="field_decline", zone="field", severity=severity,
                 evidence={"decline_pct": 20.0})


class TestEscalation:
    def test_dry_forecast_escalates_and_tags(self) -> None:
        weather = WeatherSummary(rain_next_7d_mm=1.0, rain_past_14d_mm=3.0)
        result = apply_weather(_alert("low"), weather)
        assert result.severity == "medium"
        assert result.evidence["likely_water_stress"] is True
        assert result.evidence["rain_next_7d_mm"] == 1.0
        assert result.evidence["rain_past_14d_mm"] == 3.0

    def test_wet_forecast_records_rain_but_does_not_escalate(self) -> None:
        weather = WeatherSummary(rain_next_7d_mm=25.0, rain_past_14d_mm=40.0)
        result = apply_weather(_alert("low"), weather)
        assert result.severity == "low"
        assert "likely_water_stress" not in result.evidence
        assert result.evidence["rain_next_7d_mm"] == 25.0

    @pytest.mark.parametrize(
        ("start", "expected"),
        [("low", "medium"), ("medium", "high"), ("high", "high")],
    )
    def test_severity_bump_saturates_at_high(self, start: str, expected: str) -> None:
        dry = WeatherSummary(rain_next_7d_mm=0.0, rain_past_14d_mm=0.0)
        assert apply_weather(_alert(start), dry).severity == expected

    def test_threshold_boundary_is_not_dry(self) -> None:
        at_threshold = WeatherSummary(rain_next_7d_mm=DRY_THRESHOLD_MM, rain_past_14d_mm=0.0)
        assert apply_weather(_alert("low"), at_threshold).severity == "low"

    def test_original_evidence_is_preserved(self) -> None:
        weather = WeatherSummary(rain_next_7d_mm=1.0, rain_past_14d_mm=1.0)
        result = apply_weather(_alert("medium"), weather)
        assert result.evidence["decline_pct"] == 20.0


class TestCache:
    def test_second_call_within_ttl_is_served_from_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        weather_client.clear_cache()
        calls = {"n": 0}

        async def fake_request(lat: float, lon: float) -> WeatherSummary:
            calls["n"] += 1
            return WeatherSummary(rain_next_7d_mm=2.0, rain_past_14d_mm=5.0)

        monkeypatch.setattr(weather_client, "_request", fake_request)

        now = datetime(2026, 7, 16, tzinfo=UTC)
        asyncio.run(fetch_weather(10.85, 79.20, now=now))
        asyncio.run(fetch_weather(10.85, 79.20, now=now + timedelta(hours=3)))
        assert calls["n"] == 1

    def test_expired_cache_refetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        weather_client.clear_cache()
        calls = {"n": 0}

        async def fake_request(lat: float, lon: float) -> WeatherSummary:
            calls["n"] += 1
            return WeatherSummary(rain_next_7d_mm=2.0, rain_past_14d_mm=5.0)

        monkeypatch.setattr(weather_client, "_request", fake_request)

        now = datetime(2026, 7, 16, tzinfo=UTC)
        asyncio.run(fetch_weather(10.85, 79.20, now=now))
        asyncio.run(fetch_weather(10.85, 79.20, now=now + CACHE_TTL + timedelta(minutes=1)))
        assert calls["n"] == 2
