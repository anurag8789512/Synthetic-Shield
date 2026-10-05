"""Fusion engine: normalize → weighted sum → worst-signal escalation → routing (spec §6)."""
from __future__ import annotations

from app.scoring.config import ScoringConfig
from app.scoring.models import Finding, RoutingBand, SubScore

# Virtual signal floor for escalation-eligible findings (C-H3 external web match).
ESCALATION_VIRTUAL_FLOOR = 92.0


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def normalize(sub: SubScore) -> SubScore:
    """All sub-scores arrive on 0-100, higher = more suspicious.

    This is the single place min-max rescaling would be added for a future
    provider on another scale; kept explicit even while near-identity.
    """
    if sub.status == "ok" and sub.value is not None:
        sub.value = clamp(float(sub.value))
    return sub


def fuse(subscores: list[SubScore], config: ScoringConfig,
         forced_review_reasons: list[str] | None = None) -> dict:
    """Compute base score, escalation, and routing band from sub-scores.

    Returns dict with: base_score, final_score, escalated, escalation_source,
    routing_band, weights_used, forced_review_reason.
    """
    fusion_cfg = config.fusion
    subscores = [normalize(s) for s in subscores]
    ok = [s for s in subscores if s.status == "ok" and s.value is not None]

    # §6.4 re-normalization over available signals
    available_weight = sum(fusion_cfg.weights[s.name] for s in ok)
    if ok and available_weight > 0:
        weights_used = {s.name: fusion_cfg.weights[s.name] / available_weight for s in ok}
        base = sum(weights_used[s.name] * s.value for s in ok)
    else:
        weights_used = {}
        base = 0.0
    base = clamp(base)

    # §6.3 worst-signal escalation — only AI-manipulation signals (config
    # fusion.escalation_signals) can escalate; findings explicitly marked
    # escalation_eligible (C-H3 external web match) are the designed exception.
    candidates: list[tuple[str, float]] = [
        (s.name, s.value) for s in ok if s.name in fusion_cfg.escalation_signals
    ]
    for s in ok:
        for f in s.findings:
            if f.escalation_eligible:
                candidates.append((f"{s.name}:{f.rule_id}", max(s.value, ESCALATION_VIRTUAL_FLOOR)))

    escalated = False
    escalation_source: str | None = None
    final = base
    if candidates:
        source, s_max = max(candidates, key=lambda c: c[1])
        if s_max >= fusion_cfg.escalation_threshold:
            escalated = True
            escalation_source = source.split(":")[0]
            final = max(base, s_max - fusion_cfg.escalation_discount)
    final = clamp(final)

    # §6.5 routing — the engine only routes; it never denies.
    routing = fusion_cfg.routing
    if final < routing.auto_approve_below:
        band: RoutingBand = "AUTO_APPROVE"
    elif final > routing.siu_above:
        band = "SIU_INVESTIGATION"
    else:
        band = "HUMAN_REVIEW"

    # §6.4 forced-review overrides: only ever upgrade AUTO_APPROVE → HUMAN_REVIEW
    forced_reason = None
    reasons = list(forced_review_reasons or [])
    unavailable_count = sum(1 for s in subscores if s.status == "unavailable")
    if unavailable_count >= 3:
        reasons.append(f"{unavailable_count} of {len(subscores)} sub-scores unavailable")
    if reasons:
        forced_reason = "; ".join(reasons)
        if band == "AUTO_APPROVE":
            band = "HUMAN_REVIEW"

    return {
        "base_score": base,
        "final_score": final,
        "escalated": escalated,
        "escalation_source": escalation_source,
        "routing_band": band,
        "weights_used": weights_used,
        "forced_review_reason": forced_reason,
    }
