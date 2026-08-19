"""
Mock detection providers for all modalities.
Returns deterministic-but-varied scores seeded from filename content.
Filenames containing 'fraud' force high scores; 'clean' forces low scores.
"""
import asyncio
import hashlib
from app.config import settings


def _score_from_seed(seed: str) -> float:
    """Derive a 0-100 score from a string seed for consistent demo results."""
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return round((h % 10000) / 100, 1)


def _apply_overrides(filename: str, base_score: float) -> float:
    """Force specific outcomes based on trigger words in filenames."""
    name = filename.lower()
    if "fraud" in name or "fake" in name or "synthetic" in name:
        return min(95.0, max(85.1, base_score + 60))
    if "clean" in name or "real" in name or "genuine" in name:
        return max(2.0, min(14.9, base_score - 60))
    return base_score


async def analyze_video(filename: str, content: bytes) -> dict:
    await asyncio.sleep(settings.DETECTION_SIMULATED_DELAY_SECONDS * 0.4)
    score = _apply_overrides(filename, _score_from_seed(f"video:{filename}:{len(content)}"))
    findings = []
    if score > 50:
        findings.append({"detail": "Frame-level diffusion artifacts detected at 0:11-0:14", "timestamp_or_location": "0:11-0:14"})
    if score > 75:
        findings.append({"detail": "Inconsistent specular reflections on damaged region — synthetic generation signature", "timestamp_or_location": "0:08-0:16"})
    if score > 90:
        findings.append({"detail": "EXIF metadata absent — image fingerprint matches Stable Diffusion v2.1 pipeline", "timestamp_or_location": None})
    return {"raw_score": score, "findings": findings}


async def analyze_audio(filename: str, content: bytes) -> dict:
    await asyncio.sleep(settings.DETECTION_SIMULATED_DELAY_SECONDS * 0.3)
    score = _apply_overrides(filename, _score_from_seed(f"audio:{filename}:{len(content)}"))
    findings = []
    if score > 40:
        findings.append({"detail": "Slight audio frequency variance detected at 0:04-0:06", "timestamp_or_location": "0:04-0:06"})
    if score > 70:
        findings.append({"detail": "Synthetic frequency gaps in voice statement — voice clone probability high", "timestamp_or_location": "0:02-0:05"})
    if score > 85:
        findings.append({"detail": "Spectral signature matches TTS voice-clone pattern. Pitch variance at 3.2σ", "timestamp_or_location": "0:03-0:07"})
    return {"raw_score": score, "findings": findings}


async def analyze_image(filename: str, content: bytes) -> dict:
    await asyncio.sleep(settings.DETECTION_SIMULATED_DELAY_SECONDS * 0.2)
    score = _apply_overrides(filename, _score_from_seed(f"image:{filename}:{len(content)}"))
    findings = []
    if score > 50:
        findings.append({"detail": "Minor lighting inconsistency in damage region", "timestamp_or_location": "bumper area"})
    if score > 80:
        findings.append({"detail": "Pixel-level GAN artifacts consistent with AI image generation", "timestamp_or_location": "full frame"})
    return {"raw_score": score, "findings": findings}


async def analyze_text(text: str) -> dict:
    await asyncio.sleep(settings.DETECTION_SIMULATED_DELAY_SECONDS * 0.1)
    score = _apply_overrides(text[:20], _score_from_seed(f"text:{text[:100]}"))
    findings = []
    if score > 60:
        findings.append({"detail": "Elevated perplexity uniformity — possible AI-generated narrative", "timestamp_or_location": None})
    return {"raw_score": score, "findings": findings}
