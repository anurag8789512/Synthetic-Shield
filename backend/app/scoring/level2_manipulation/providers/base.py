"""DetectorProvider ABC + retry helper + deterministic mock (spec §9).

Every foreign detector call goes through a provider selected by env var.
Providers log (provider, latency, status) but never media bytes or API keys.
"""
from __future__ import annotations

import abc
import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    raw_score: float          # in [0, 1]
    label: str
    latency_ms: float
    provider_name: str
    provider_version: str = "v1"
    extra: dict = field(default_factory=dict)


class ProviderError(Exception):
    pass


class DetectorProvider(abc.ABC):
    provider_name: str = "base"
    # Direction constant asserted in tests: True → raw_score is probability-of-FAKE.
    SCORE_IS_FAKE_PROBABILITY: bool = True

    @abc.abstractmethod
    async def detect(self, filename: str, content: bytes) -> ProviderResult: ...

    async def health(self) -> bool:
        return True


async def call_with_retries(coro_factory, retries: int, timeout_s: float,
                            provider_name: str) -> ProviderResult:
    """Run provider call with timeout + exponential-backoff retries."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(coro_factory(), timeout=timeout_s)
            print(f"[SCORING] provider={provider_name} status=ok latency_ms={(time.monotonic()-start)*1000:.0f}")
            return result
        except Exception as e:
            last_exc = e
            print(f"[SCORING] provider={provider_name} status=error attempt={attempt + 1} err={type(e).__name__}")
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
    raise ProviderError(f"{provider_name} failed after {retries + 1} attempts") from last_exc


class MockDetectorProvider(DetectorProvider):
    """Deterministic canned responses for tests and demo mode.

    Filename containing the whole word fraud|fake|synthetic → high fake
    probability; clean|real|genuine → low; otherwise seeded from the content hash
    in [0, 0.6) so an untriggered mock can never escalate a claim on its own.
    Claimant text is never keyword-matched (a statement saying "fake" isn't fake).
    """
    SCORE_IS_FAKE_PROBABILITY = True

    def __init__(self, provider_name: str = "mock"):
        self.provider_name = provider_name

    async def detect(self, filename: str, content: bytes) -> ProviderResult:
        key = filename.lower()

        def hit(words):
            return any(re.search(rf"(?<![a-z]){w}(?![a-z])", key) for w in words)

        if hit(("fraud", "fake", "synthetic")):
            score = 0.93
        elif hit(("clean", "real", "genuine")):
            score = 0.05
        else:
            digest = hashlib.md5(filename.encode() + content[:256]).hexdigest()
            score = (int(digest[:8], 16) % 600) / 1000.0
        return ProviderResult(raw_score=score, label="fake" if score > 0.5 else "real",
                              latency_ms=1.0, provider_name=self.provider_name,
                              provider_version="mock-1")
