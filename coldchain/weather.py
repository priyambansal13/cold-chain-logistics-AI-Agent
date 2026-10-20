"""Live weather from the Open-Meteo forecast API (free, no API key) + threat flagging."""
from __future__ import annotations

import requests

from .config import HEATWAVE_REGIONS, HTTP_TIMEOUT_S, OPEN_METEO_URL

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog",
    48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Freezing drizzle", 57: "Dense freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers",
    81: "Heavy rain showers", 82: "Violent rain showers", 85: "Snow showers",
    86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


def threat_flags(max_c: float, min_c: float, precip_mm: float, wind_kmh: float, code: int) -> list[str]:
    flags = []
    if max_c >= 40:
        flags.append("EXTREME_HEAT")
    elif max_c >= 35:
        flags.append("SEVERE_HEAT")
    elif max_c >= 30:
        flags.append("ELEVATED_HEAT")
    if min_c <= -15:
        flags.append("EXTREME_COLD")
    if precip_mm >= 25:
        flags.append("HEAVY_PRECIPITATION")
    if wind_kmh >= 60:
        flags.append("HIGH_WIND")
    if code in (95, 96, 99):
        flags.append("THUNDERSTORM")
    if code in (56, 57, 66, 67, 71, 73, 75, 77, 85, 86):
        flags.append("SNOW_OR_ICE")
    return flags


def _in_region(lat: float, lon: float, region: str) -> bool:
    box = HEATWAVE_REGIONS.get(region)
    return bool(box) and box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]


def fetch_forecast(points: list[dict], days: int = 3, scenario: dict | None = None) -> list[dict]:
    """Fetch current conditions + daily forecast for several {name, lat, lon} points in one call.

    `scenario` (optional) = {"enabled": bool, "delta_c": float, "region": str} overlays a
    simulated heatwave on top of live data for drills/demos; overlaid values are labelled.
    """
    if not points:
        return []
    params = {
        "latitude": ",".join(f"{p['lat']:.4f}" for p in points),
        "longitude": ",".join(f"{p['lon']:.4f}" for p in points),
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code",
        "timezone": "auto",
        "forecast_days": days,
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    payload = resp.json()
    payload = payload if isinstance(payload, list) else [payload]

    results = []
    for p, w in zip(points, payload):
        cur, daily = w.get("current", {}), w.get("daily", {})
        overlay = 0.0
        if scenario and scenario.get("enabled") and _in_region(p["lat"], p["lon"], scenario.get("region", "")):
            overlay = float(scenario.get("delta_c", 0))
        days_out = []
        for i, date in enumerate(daily.get("time", [])):
            tmax = daily["temperature_2m_max"][i] + overlay
            tmin = daily["temperature_2m_min"][i] + overlay
            code = int(daily["weather_code"][i] or 0)
            precip = daily["precipitation_sum"][i] or 0.0
            wind = daily["wind_speed_10m_max"][i] or 0.0
            days_out.append({
                "date": date,
                "max_c": round(tmax, 1),
                "min_c": round(tmin, 1),
                "precip_mm": precip,
                "wind_max_kmh": wind,
                "conditions": WEATHER_CODES.get(code, f"code {code}"),
                "threat_flags": threat_flags(tmax, tmin, precip, wind, code),
            })
        result = {
            **p,
            "current": {
                "temp_c": round((cur.get("temperature_2m") or 0) + overlay, 1),
                "humidity_pct": cur.get("relative_humidity_2m"),
                "wind_kmh": cur.get("wind_speed_10m"),
                "conditions": WEATHER_CODES.get(int(cur.get("weather_code") or 0), "n/a"),
            },
            "daily": days_out,
        }
        if overlay:
            result["scenario_overlay"] = f"+{overlay:.0f} °C simulated heatwave ({scenario['region']})"
        results.append(result)
    return results
