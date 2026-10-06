"""Historical weather provider (swappable, spec §5.2 C-H2)."""
from __future__ import annotations

import abc
from datetime import datetime

import httpx

from app.config import settings


class WeatherProvider(abc.ABC):
    provider_name = "base"

    @abc.abstractmethod
    async def had_event(self, lat: float, lon: float, when: datetime,
                        event: str, window_h: float) -> bool | None:
        """True/False if determinable, None if the lookup is unavailable."""

    async def health(self) -> bool:
        return True


class OpenWeatherProvider(WeatherProvider):
    provider_name = "openweather"
    # OpenWeather condition-code groups per claimed event type
    EVENT_CODES = {
        "hail": {906, 511},           # hail / freezing rain
        "storm": set(range(200, 233)) | {771, 781},
        "rain": set(range(500, 532)),
        "flood": set(range(500, 532)) | {771},  # proxy: extreme rain events
    }

    async def had_event(self, lat: float, lon: float, when: datetime,
                        event: str, window_h: float) -> bool | None:
        if not settings.OPENWEATHER_API_KEY:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/3.0/onecall/timemachine",
                    params={"lat": lat, "lon": lon, "dt": int(when.timestamp()),
                            "appid": settings.OPENWEATHER_API_KEY},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None
        codes = {w.get("id") for entry in data.get("data", [])
                 for w in entry.get("weather", [])}
        target = self.EVENT_CODES.get(event, set())
        return bool(codes & target)


class MockWeatherProvider(WeatherProvider):
    """Deterministic stand-in. Confirms claimed weather by default (demo claims
    never get a fabricated C-H2); pass contradicted_events={"hail", ...} to
    simulate records that contradict specific claims."""
    provider_name = "mock"

    def __init__(self, contradicted_events: set[str] | None = None):
        self.contradicted_events = set(contradicted_events or ())

    async def had_event(self, lat: float, lon: float, when: datetime,
                        event: str, window_h: float) -> bool | None:
        return event not in self.contradicted_events


def get_weather_provider() -> WeatherProvider:
    name = settings.WEATHER_PROVIDER
    if name == "openweather":
        return OpenWeatherProvider()
    if name == "mock":
        return MockWeatherProvider()
    raise ValueError(f"unknown WEATHER_PROVIDER: {name}")
