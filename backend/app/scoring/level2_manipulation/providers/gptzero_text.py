"""GPTZero text detector provider — primary S_text detector (spec §4.4)."""
from __future__ import annotations

import time

import httpx

from app.config import settings
from app.scoring.level2_manipulation.providers.base import DetectorProvider, ProviderError, ProviderResult

API_URL = "https://api.gptzero.me/v2/predict/text"


class GPTZeroTextProvider(DetectorProvider):
    provider_name = "gptzero"
    # GPTZero returns completely_generated_prob = probability text is AI-generated.
    SCORE_IS_FAKE_PROBABILITY = True

    def __init__(self, timeout_s: float = 30):
        self.timeout_s = timeout_s

    async def detect(self, filename: str, content: bytes) -> ProviderResult:
        api_key = settings.GPTZERO_API_KEY
        if not api_key:
            raise ProviderError("GPTZERO_API_KEY not configured")
        text = content.decode("utf-8", "ignore")
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                API_URL,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={"document": text, "multilingual": False},
            )
            resp.raise_for_status()
            data = resp.json()
        doc = (data.get("documents") or [{}])[0]
        raw = doc.get("completely_generated_prob")
        if raw is None:
            cp = doc.get("class_probabilities") or {}
            raw = cp.get("ai", 0.0)
        raw = min(max(float(raw), 0.0), 1.0)
        return ProviderResult(
            raw_score=raw, label=doc.get("predicted_class") or ("ai" if raw > 0.5 else "human"),
            latency_ms=(time.monotonic() - start) * 1000,
            provider_name=self.provider_name,
        )
