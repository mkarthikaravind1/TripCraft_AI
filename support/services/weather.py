"""
Destination weather via the Open-Meteo API (https://open-meteo.com, no API key).

Two calls: geocoding (destination name -> coordinates) and the daily forecast
for the trip dates. Every call has a short timeout; any failure returns a
clear "unavailable" result instead of invented weather. Results are cached
briefly and always carry the time they were fetched.
"""

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 16  # Open-Meteo forecast horizon
CACHE_SECONDS = 30 * 60

# WMO weather interpretation codes (subset used by Open-Meteo).
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
    82: "Violent rain showers", 85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


class WeatherError(Exception):
    pass


@dataclass
class WeatherResult:
    status: str  # ok | partial | out_of_range | not_found | unavailable
    message: str
    location: str = ""
    days: list = field(default_factory=list)
    fetched_at: str = ""
    source: str = "Open-Meteo"

    def as_dict(self):
        return asdict(self)


def _get_json(url, params):
    try:
        response = requests.get(url, params=params, timeout=settings.WEATHER_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.Timeout as exc:
        raise WeatherError("timeout") from exc
    except requests.RequestException as exc:
        raise WeatherError(type(exc).__name__) from exc
    except ValueError as exc:  # invalid JSON
        raise WeatherError("invalid JSON") from exc


def geocode(name):
    query = name.split(",")[0].strip()
    data = _get_json(GEOCODE_URL, {"name": query, "count": 1, "language": "en", "format": "json"})
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return None
    first = results[0]
    try:
        lat, lon = float(first["latitude"]), float(first["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("invalid geocoding data") from exc
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise WeatherError("invalid coordinates")
    label = ", ".join(str(p) for p in (first.get("name"), first.get("country")) if p)
    return lat, lon, label


def _parse_daily(data, start, end):
    daily = data.get("daily") if isinstance(data, dict) else None
    if not isinstance(daily, dict):
        raise WeatherError("missing daily data")
    times = daily.get("time") or []
    columns = {k: daily.get(k) or [] for k in ("weather_code", "temperature_2m_max", "temperature_2m_min",
                                                "precipitation_probability_max")}
    days = []
    for i, iso in enumerate(times):
        try:
            day = date.fromisoformat(iso)
        except (TypeError, ValueError):
            continue
        if not (start <= day <= end):
            continue
        def value(key):
            col = columns[key]
            return col[i] if i < len(col) and isinstance(col[i], (int, float)) else None
        t_max, t_min = value("temperature_2m_max"), value("temperature_2m_min")
        if t_max is None or t_min is None:
            continue
        code = value("weather_code")
        days.append({
            "date": iso,
            "summary": WEATHER_CODES.get(int(code), "Mixed conditions") if code is not None else "Conditions unavailable",
            "temp_max": round(t_max),
            "temp_min": round(t_min),
            "rain_chance": round(value("precipitation_probability_max")) if value("precipitation_probability_max") is not None else None,
        })
    return days


def get_forecast(destination, start, end, today=None):
    """Forecast for the trip dates, or a clear explanation of why there isn't one."""
    today = today or timezone.localdate()
    horizon = today + timedelta(days=FORECAST_DAYS - 1)
    if start > horizon:
        return WeatherResult(
            status="out_of_range",
            message=f"Forecasts are only available up to {FORECAST_DAYS} days ahead. Check back from "
                    f"{(start - timedelta(days=FORECAST_DAYS - 1)):%d %b %Y} for your trip dates.",
        )
    if end < today:
        return WeatherResult(status="out_of_range", message="These trip dates are in the past, so no forecast is shown.")

    cache_key = "weather:" + hashlib.sha256(f"{destination.lower()}|{start}|{end}|{today}".encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached:
        return WeatherResult(**cached)

    try:
        place = geocode(destination)
        if place is None:
            result = WeatherResult(status="not_found", message=f"We couldn't find “{destination}” in the weather service.")
            cache.set(cache_key, result.as_dict(), CACHE_SECONDS)
            return result
        lat, lon, label = place
        window_start, window_end = max(start, today), min(end, horizon)
        data = _get_json(FORECAST_URL, {
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "start_date": window_start.isoformat(), "end_date": window_end.isoformat(),
        })
        days = _parse_daily(data, window_start, window_end)
    except WeatherError as exc:
        logger.warning("Weather lookup failed: %s", exc)
        return WeatherResult(status="unavailable",
                             message="Weather information is temporarily unavailable. Your itinerary is unaffected.")

    if not days:
        return WeatherResult(status="unavailable", location=label,
                             message="The weather service returned no forecast for these dates.")
    covered_all = window_start == start and window_end == end and len(days) == (end - start).days + 1
    result = WeatherResult(
        status="ok" if covered_all else "partial",
        message="" if covered_all else "Forecast covers only the trip days within the next 16 days.",
        location=label,
        days=days,
        fetched_at=timezone.now().isoformat(timespec="minutes"),
    )
    cache.set(cache_key, result.as_dict(), CACHE_SECONDS)
    return result
