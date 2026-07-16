"""Open-Meteo precipitation at a field centroid, cached per location.

Keyless. One call returns 14 past days plus a 7-day forecast of daily
precipitation; we reduce it to two sums. Results are cached for 6 hours per
rounded centroid so repeated refreshes of the same field do not re-hit the API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_URL: Final = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS: Final = 14
FORECAST_DAYS: Final = 7
CACHE_TTL: Final = timedelta(hours=6)
# ~1 km grid: fields closer than this share a cache entry, which is well within
# the resolution at which precipitation forecasts vary.
_CACHE_PRECISION: Final = 2


class WeatherError(RuntimeError):
    """Weather could not be retrieved."""


@dataclass(frozen=True)
class WeatherSummary:
    rain_next_7d_mm: float
    rain_past_14d_mm: float


_cache: dict[tuple[float, float], tuple[datetime, WeatherSummary]] = {}


def parse_daily(daily: dict[str, Any], today: date) -> WeatherSummary:
    """Split Open-Meteo daily precipitation into past-14d and next-7d sums.

    Missing daily values (null) are treated as 0 mm rather than dropped, so a
    gap does not silently shorten the window.
    """
    times = daily.get("time")
    precip = daily.get("precipitation_sum")
    if not isinstance(times, list) or not isinstance(precip, list) or len(times) != len(precip):
        raise WeatherError("Unexpected weather response shape.")

    horizon = today + timedelta(days=FORECAST_DAYS)
    past = 0.0
    upcoming = 0.0
    for time_str, value in zip(times, precip, strict=True):
        try:
            day = date.fromisoformat(str(time_str))
        except ValueError as exc:
            raise WeatherError("Unparseable date in weather response.") from exc
        mm = float(value) if value is not None else 0.0
        if day < today:
            past += mm
        elif today <= day < horizon:
            upcoming += mm

    return WeatherSummary(
        rain_next_7d_mm=round(upcoming, 1),
        rain_past_14d_mm=round(past, 1),
    )


async def _request(lat: float, lon: float) -> WeatherSummary:
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        raise WeatherError("Could not reach the weather service.") from exc

    daily = body.get("daily")
    if not isinstance(daily, dict):
        raise WeatherError("Weather response had no daily data.")
    return parse_daily(daily, datetime.now(UTC).date())


async def fetch_weather(lat: float, lon: float, *, now: datetime | None = None) -> WeatherSummary:
    """Precipitation summary at (lat, lon), cached 6 h per rounded location."""
    now = now or datetime.now(UTC)
    key = (round(lat, _CACHE_PRECISION), round(lon, _CACHE_PRECISION))

    cached = _cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]

    summary = await _request(lat, lon)
    _cache[key] = (now + CACHE_TTL, summary)
    return summary


def clear_cache() -> None:
    """Drop all cached weather (used by tests)."""
    _cache.clear()
