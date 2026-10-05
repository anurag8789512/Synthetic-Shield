"""Local speech-to-text for voice-statement fact extraction (spec §5.1).

STT is allowed for fact extraction only — never for scoring judgments.
Swappable via STT_PROVIDER env var; failures degrade to no transcript.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import settings


@lru_cache(maxsize=1)
def _whisper_model():
    from faster_whisper import WhisperModel
    # small CPU-friendly model; downloaded on first use and cached locally
    return WhisperModel("base", device="cpu", compute_type="int8")


def transcribe(audio_path: str | Path) -> str | None:
    """Return transcript text, or None when STT is disabled/unavailable."""
    provider = settings.STT_PROVIDER
    if provider == "none":
        return None
    if provider == "mock":
        return None  # tests inject transcripts directly on the claim
    if provider == "faster_whisper":
        try:
            segments, _info = _whisper_model().transcribe(str(audio_path), beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text or None
        except Exception as e:
            print(f"[SCORING] stt provider=faster_whisper status=error err={type(e).__name__}")
            return None
    raise ValueError(f"unknown STT_PROVIDER: {provider}")
