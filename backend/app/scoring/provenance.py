"""C2PA content-credential reading (local, via c2pa-python). NO network calls.

Used by Level 1 (M-C1 credit / M-H6 AI declaration) and Level 2 (image/video
synthesis evidence). Generators such as OpenAI, Google and Adobe Firefly embed a
manifest whose actions carry an IPTC digitalSourceType of trainedAlgorithmicMedia.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# IPTC digital source types meaning "made (wholly or partly) by a generative model"
AI_SOURCE_TYPES = ("trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia")


@dataclass(frozen=True)
class C2PAInfo:
    ai_generated: bool
    valid: bool                # manifest validated with no errors (incl. trusted signer)
    generator: str | None
    validation_errors: tuple[str, ...]


def read_c2pa(path: str | Path) -> C2PAInfo | None:
    """C2PA summary for a file, or None if no manifest / c2pa-python unavailable."""
    p = Path(path)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    return _read_cached(str(p), mtime)


@lru_cache(maxsize=256)
def _read_cached(path: str, mtime: float) -> C2PAInfo | None:  # noqa: ARG001 (mtime = cache key)
    try:
        import c2pa  # type: ignore
    except ImportError:
        return None
    try:
        reader = c2pa.Reader(path)
    except Exception:
        return None  # no manifest, or unsupported format
    try:
        raw = reader.json()
    except Exception:
        return None
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    active = (data.get("manifests") or {}).get(data.get("active_manifest") or "", {})
    generator = active.get("claim_generator") or ", ".join(
        i.get("name", "") for i in active.get("claim_generator_info") or [] if i.get("name")
    ) or None
    errors = tuple(v.get("code", "") for v in data.get("validation_status") or [])
    return C2PAInfo(
        ai_generated=any(t in raw for t in AI_SOURCE_TYPES),
        valid=not errors,
        generator=generator,
        validation_errors=errors,
    )
