"""Data contracts for the scoring engine (spec §7)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SubScoreName = Literal["metadata", "image", "video", "audio", "text", "consistency"]
# Exactly three routing bands. No denial output exists anywhere in this module.
RoutingBand = Literal["AUTO_APPROVE", "HUMAN_REVIEW", "SIU_INVESTIGATION"]


class Finding(BaseModel):
    rule_id: str
    severity: Literal["high", "medium", "low", "credit", "info"]
    points: float
    file_id: str | None = None
    human_readable: str
    escalation_eligible: bool = False
    extra: dict = Field(default_factory=dict)


class SubScore(BaseModel):
    name: SubScoreName
    value: float | None = None  # 0..100, None unless status == "ok"
    status: Literal["ok", "unavailable", "not_applicable"] = "ok"
    findings: list[Finding] = Field(default_factory=list)
    provider: str | None = None
    components: dict[str, float] = Field(default_factory=dict)


class RoutingDecision(BaseModel):
    band: RoutingBand
    forced_review_reason: str | None = None


class ScoreBreakdown(BaseModel):
    claim_id: str
    version: int
    config_version: str
    subscores: list[SubScore]
    weights_used: dict[str, float]  # post re-normalization
    base_score: float
    final_score: float
    escalated: bool
    escalation_source: str | None = None
    routing_band: RoutingBand
    forced_review_reason: str | None = None
    payout_cap: float | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
