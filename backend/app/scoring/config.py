"""Pydantic models + YAML loader for scoring_config.yaml.

Loaded once at startup; validated. config_version is stored with every score row.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Literal

import yaml
from pydantic import BaseModel, model_validator


class RoutingConfig(BaseModel):
    auto_approve_below: float = 15
    siu_above: float = 85

    @model_validator(mode="after")
    def _ordered(self):
        if not (0 <= self.auto_approve_below < self.siu_above <= 100):
            raise ValueError("routing thresholds must satisfy 0 <= auto < siu <= 100")
        return self


class FusionConfig(BaseModel):
    weights: Dict[str, float]
    escalation_threshold: float = 90
    escalation_discount: float = 5
    escalation_signals: list[str] = ["image", "video", "audio", "text"]
    routing: RoutingConfig

    @model_validator(mode="after")
    def _weights_sum(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"fusion.weights must sum to 1.0, got {total}")
        expected = {"image", "video", "audio", "consistency", "metadata", "text"}
        if set(self.weights) != expected:
            raise ValueError(f"fusion.weights keys must be {expected}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("fusion weights must be >= 0")
        if not set(self.escalation_signals) <= expected:
            raise ValueError("fusion.escalation_signals must be a subset of the weight keys")
        return self


class MetadataCredits(BaseModel):
    c2pa: float = -25
    intact_exif: float = -8

    @model_validator(mode="after")
    def _negative(self):
        if self.c2pa > 0 or self.intact_exif > 0:
            raise ValueError("credits must be <= 0")
        return self


class MetadataConfig(BaseModel):
    high: float = 35
    medium: float = 20
    low: float = 8
    credits: MetadataCredits = MetadataCredits()
    gps_radius_km: float = 25
    phash_threshold: int = 6
    modify_gap_hours: float = 1

    @model_validator(mode="after")
    def _penalties_positive(self):
        if any(v < 0 for v in (self.high, self.medium, self.low)):
            raise ValueError("metadata penalties must be >= 0")
        return self


class RampConfig(BaseModel):
    """Linear ramp bounds: score = clamp((x - lo) / (hi - lo), 0, 1) * 100."""
    r0: float | None = None
    r1: float | None = None
    p0: float | None = None
    p1: float | None = None
    n0: float | None = None
    n1: float | None = None
    lo: float | None = None
    hi: float | None = None
    quality: int | None = None


class ImagePixelConfig(BaseModel):
    component_weights: Dict[str, float]   # editing group
    synthesis_weights: Dict[str, float]
    ela: RampConfig
    dq: RampConfig
    noise: RampConfig
    texture: RampConfig
    clipping: RampConfig
    saturation: RampConfig

    @model_validator(mode="after")
    def _weights(self):
        for field, expected in (("component_weights", {"ela", "jpeg_dq", "noise"}),
                                ("synthesis_weights", {"texture", "clipping", "saturation"})):
            weights = getattr(self, field)
            if set(weights) != expected:
                raise ValueError(f"image_pixel.{field} keys must be {expected}")
            if abs(sum(weights.values()) - 1.0) > 1e-9:
                raise ValueError(f"image_pixel.{field} must sum to 1.0")
        for name in ("texture", "clipping", "saturation"):
            ramp = getattr(self, name)
            if ramp.lo is None or ramp.hi is None or ramp.hi <= ramp.lo:
                raise ValueError(f"image_pixel.{name} needs lo < hi")
        return self


class VideoPixelConfig(BaseModel):
    fps_sample: float = 1
    max_frames: int = 60
    min_anomalous_frames: int = 3


class ProvidersConfig(BaseModel):
    timeout_s: float = 30
    retries: int = 2


class TextConfig(BaseModel):
    min_chars: int = 300
    disagreement_gap: float = 25


class ConsistencyConfig(BaseModel):
    weather_window_h: float = 6
    temporal_gap_h: float = 2
    external_reverse_search: Literal["always", "suspicious_only"] = "suspicious_only"


class PricingConfig(BaseModel):
    cache_days: int = 7
    labor_buffer: float = 0.35
    min_price_points: int = 3


class ScoringConfig(BaseModel):
    config_version: str
    fusion: FusionConfig
    metadata: MetadataConfig
    image_pixel: ImagePixelConfig
    video_pixel: VideoPixelConfig
    providers: ProvidersConfig
    text: TextConfig
    consistency: ConsistencyConfig
    pricing: PricingConfig


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "scoring_config.yaml"


def load_config(path: str | Path | None = None) -> ScoringConfig:
    cfg_path = Path(path or os.environ.get("SCORING_CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ScoringConfig.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> ScoringConfig:
    return load_config()
