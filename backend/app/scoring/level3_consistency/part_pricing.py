"""Per-part market price verification via swappable provider (spec §5.4).

Privacy: queries contain only vehicle/part/region terms — never claimant PII.
"""
from __future__ import annotations

import abc
import re
import statistics
import time

import httpx

from app.config import settings


class PartPricingProvider(abc.ABC):
    provider_name = "base"

    @abc.abstractmethod
    async def lookup(self, query: str) -> list[float]:
        """Return raw market price points (same currency as claims) for the query."""

    async def health(self) -> bool:
        return True


_PRICE_RE = re.compile(r"[\$₹]\s?([\d,]+(?:\.\d{1,2})?)")


class SerpApiPartPricingProvider(PartPricingProvider):
    provider_name = "serpapi"

    async def lookup(self, query: str) -> list[float]:
        if not settings.SERPAPI_API_KEY:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://serpapi.com/search",
                    params={"engine": "google", "q": query,
                            "api_key": settings.SERPAPI_API_KEY, "num": 10},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []
        prices: list[float] = []
        for item in (data.get("shopping_results") or []):
            p = item.get("extracted_price")
            if p:
                prices.append(float(p))
        for item in (data.get("organic_results") or []):
            snippet = f"{item.get('title', '')} {item.get('snippet', '')}"
            for m in _PRICE_RE.finditer(snippet):
                try:
                    prices.append(float(m.group(1).replace(",", "")))
                except ValueError:
                    continue
        return [p for p in prices if 1 <= p <= 1_000_000]


class MockPartPricingProvider(PartPricingProvider):
    provider_name = "mock"
    CANNED = {"front_bumper": [320.0, 410.0, 380.0], "rear_bumper": [300.0, 350.0, 390.0],
              "windshield": [250.0, 300.0, 280.0], "headlight": [150.0, 210.0, 180.0]}

    async def lookup(self, query: str) -> list[float]:
        for part, prices in self.CANNED.items():
            if part.replace("_", " ") in query:
                return prices
        return [400.0, 500.0, 450.0]


_cache: dict[str, tuple[float, list[float]]] = {}


async def get_market_estimate(part: str, vehicle: str, region: str,
                              provider: PartPricingProvider,
                              cache_days: int, min_price_points: int) -> float | None:
    """Median of parsed prices; requires >= min_price_points else None (no penalty)."""
    key = f"{vehicle}|{part}|{region}".lower()
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < cache_days * 86400:
        prices = cached[1]
    else:
        query = f"{vehicle} {part.replace('_', ' ')} replacement cost {region}".strip()
        prices = await provider.lookup(query)
        _cache[key] = (now, prices)
    if len(prices) < min_price_points:
        return None
    return float(statistics.median(prices))


def get_part_pricing_provider() -> PartPricingProvider:
    name = settings.PART_PRICING_PROVIDER
    if name == "serpapi":
        return SerpApiPartPricingProvider()
    if name == "mock":
        return MockPartPricingProvider()
    raise ValueError(f"unknown PART_PRICING_PROVIDER: {name}")
