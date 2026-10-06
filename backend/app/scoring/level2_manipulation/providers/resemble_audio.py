"""Resemble AI Detect provider for S_audio (spec §4.3)."""
from __future__ import annotations

import time

import httpx

from app.config import settings
from app.scoring.level2_manipulation.providers.base import DetectorProvider, ProviderError, ProviderResult

API_URL = "https://app.resemble.ai/api/v2/detect"


class ResembleAudioProvider(DetectorProvider):
    provider_name = "resemble"
    # Verified against Resemble Detect docs: metrics label "fake" with score =
    # probability the audio is synthetic.
    SCORE_IS_FAKE_PROBABILITY = True

    def __init__(self, timeout_s: float = 30):
        self.timeout_s = timeout_s

    async def detect(self, filename: str, content: bytes) -> ProviderResult:
        if not settings.RESEMBLE_AI_API_KEY:
            raise ProviderError("RESEMBLE_AI_API_KEY not configured")
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                API_URL,
                headers={"Authorization": f"Bearer {settings.RESEMBLE_AI_API_KEY}",
                         "Prefer": "wait"},
                files={"file": (filename, content)},
            )
            resp.raise_for_status()
            data = resp.json()
        item = data.get("item") or data
        metrics = item.get("metrics") or {}
        label = (metrics.get("label") or "").lower()
        agg = metrics.get("aggregated_score")
        if agg is not None:
            raw = float(agg)
        else:
            scores = metrics.get("score") or []
            raw = float(scores[0]) if scores else (0.95 if label == "fake" else 0.05)
        raw = min(max(raw, 0.0), 1.0)
        # direction (SCORE_IS_FAKE_PROBABILITY) is applied once, by the orchestrator
        return ProviderResult(
            raw_score=raw, label=label or ("fake" if raw > 0.5 else "real"),
            latency_ms=(time.monotonic() - start) * 1000,
            provider_name=self.provider_name,
            extra={"uuid": item.get("uuid")},
        )
