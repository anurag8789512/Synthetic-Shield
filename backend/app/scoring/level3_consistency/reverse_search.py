"""Reverse image search (spec §5.3): internal hash match first, external second.

Privacy: external queries never include claimant name, policy number, or claim ID.
"""
from __future__ import annotations

import abc

import httpx

from app.config import settings


class ReverseSearchProvider(abc.ABC):
    provider_name = "base"

    @abc.abstractmethod
    async def search(self, image_url: str) -> list[dict]:
        """Return [{"url", "title", "source"}] for confident third-party web matches."""

    async def health(self) -> bool:
        return True


class SerpApiReverseSearchProvider(ReverseSearchProvider):
    provider_name = "serpapi"

    async def search(self, image_url: str) -> list[dict]:
        if not settings.SERPAPI_API_KEY:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://serpapi.com/search",
                    params={"engine": "google_lens", "url": image_url,
                            "api_key": settings.SERPAPI_API_KEY},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []
        matches = []
        for m in (data.get("visual_matches") or [])[:10]:
            matches.append({"url": m.get("link"), "title": m.get("title"),
                            "source": m.get("source")})
        return matches


class MockReverseSearchProvider(ReverseSearchProvider):
    provider_name = "mock"

    async def search(self, image_url: str) -> list[dict]:
        return []  # no external match by default; tests monkeypatch this


def get_reverse_search_provider() -> ReverseSearchProvider:
    name = settings.REVERSE_SEARCH_PROVIDER
    if name == "serpapi":
        return SerpApiReverseSearchProvider()
    if name == "mock":
        return MockReverseSearchProvider()
    raise ValueError(f"unknown REVERSE_SEARCH_PROVIDER: {name}")
