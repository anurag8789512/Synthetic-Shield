"""Bridge between the Fraud Fusion Scoring engine and the existing claim pipeline.

Runs the deterministic scoring module, then maps its ScoreBreakdown into the
artifact_report shape the dashboard renders and the ClaimMediaAnalysis rows the
copilot consumes. The LLM report synthesizer runs strictly downstream of scoring.
"""
import json

from sqlalchemy.orm import Session as DBSession

from app.models import Claim, ClaimMediaAnalysis
from app.scoring.config import get_config
from app.scoring.models import ScoreBreakdown, SubScore
from app.scoring.orchestrator import run_scoring

BAND_TO_STATUS = {
    "AUTO_APPROVE": "auto_approved",
    "HUMAN_REVIEW": "moderator_review",
    "SIU_INVESTIGATION": "siu_investigation",
}

SUBSCORE_EXPLANATIONS = {
    "metadata": "Metadata forensics across all uploaded files (EXIF, container tags, PDF metadata, duplicate-evidence hashes).",
    "image": "In-house pixel-level forensics: editing checks (error-level analysis, JPEG double-quantization, noise consistency) and AI-synthesis checks (flat-region micro-texture, tonal clipping, saturation), plus C2PA provenance.",
    "video": "In-house frame-level forensics: per-frame pixel battery plus temporal noise and optical-flow discontinuity checks.",
    "audio": "Foreign detector verdict on voice-statement authenticity.",
    "text": "Cross-checked AI-generated-text detectors on the written statement.",
    "consistency": "Cross-evidence checks: narrative contradictions, weather records, reverse image search, per-part price verification.",
}


def _severity(score: float) -> str:
    return "low" if score < 30 else "medium" if score <= 70 else "high"


def _verdict(score: float) -> str:
    routing = get_config().fusion.routing
    if score < routing.auto_approve_below:
        return "authentic"
    return "inconclusive" if score <= routing.siu_above else "synthetic"


def _modality_report(sub: SubScore, weight: float) -> dict:
    score = sub.value if sub.value is not None else 0.0
    finding_texts = [f.human_readable for f in sub.findings]
    explanation = SUBSCORE_EXPLANATIONS.get(sub.name, "")
    if sub.components:
        comp = ", ".join(f"{k}: {v:.0f}" for k, v in sub.components.items())
        explanation += f" Component scores — {comp}."
    if sub.status != "ok":
        explanation = f"Analysis {sub.status.replace('_', ' ')}. " + explanation
    return {
        "modality": sub.name,
        "raw_score": round(score, 1),
        "severity": _severity(score),
        "verdict": _verdict(score) if sub.status == "ok" else sub.status,
        "weight": round(weight, 4),
        "provider": sub.provider or "in_house",
        "explanation": explanation,
        "findings": finding_texts,
        "timestamps": [],
        "status": sub.status,
        "components": sub.components,
    }


def build_artifact_report(breakdown: ScoreBreakdown) -> dict:
    modality_reports = [
        _modality_report(sub, breakdown.weights_used.get(sub.name, 0.0))
        for sub in breakdown.subscores
    ]
    all_findings = [f.human_readable for sub in breakdown.subscores for f in sub.findings
                    if f.severity != "info"]
    flagged = [m["modality"] for m in modality_reports
               if m["status"] == "ok" and m["severity"] != "low"]

    band = breakdown.routing_band
    if band == "AUTO_APPROVE":
        summary = ("Fusion scoring found no significant fraud signals across "
                   f"{sum(1 for s in breakdown.subscores if s.status == 'ok')} analyzed signals.")
        recommendation = "Auto-approve. No significant fraud indicators detected."
    elif band == "SIU_INVESTIGATION":
        src = f" (worst signal: {breakdown.escalation_source})" if breakdown.escalated else ""
        summary = (f"High-confidence fraud indicators detected{src}. "
                   f"Final fused score {breakdown.final_score:.0f}/100.")
        recommendation = "Route to SIU investigation for quorum review."
    else:
        reason = f" Forced review: {breakdown.forced_review_reason}." if breakdown.forced_review_reason else ""
        summary = (f"Mixed signals; fused score {breakdown.final_score:.0f}/100 requires human "
                   f"judgment.{reason}")
        recommendation = "Route to moderator for manual review."

    return {
        "fraud_confidence_score": breakdown.final_score,
        "summary": summary,
        "recommendation": recommendation,
        "detected_artifacts": all_findings,
        "modality_reports": modality_reports,
        "total_modalities_analyzed": sum(1 for s in breakdown.subscores if s.status == "ok"),
        "flagged_modalities": flagged,
        "score_breakdown": json.loads(breakdown.model_dump_json()),
    }


async def run_fusion_scoring(claim_id: int, db: DBSession) -> float:
    """Score a claim via the fusion engine, update claim fields + status, return final score."""
    breakdown = await run_scoring(claim_id, db)
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        return breakdown.final_score

    # per-signal analysis rows for copilot evidence summaries
    for sub in breakdown.subscores:
        db.add(ClaimMediaAnalysis(
            claim_id=claim_id,
            modality=sub.name,
            provider=sub.provider or "in_house",
            raw_score=sub.value,
            findings_json=json.dumps({
                "status": sub.status,
                "components": sub.components,
                "findings": [{"detail": f.human_readable, "rule_id": f.rule_id,
                              "points": f.points, "timestamp_or_location": None}
                             for f in sub.findings],
            }),
        ))

    report_dict = build_artifact_report(breakdown)

    # LLM narrative layer — downstream of the deterministic scoring path
    from app.agents.report_synthesizer import synthesize_report
    report_dict = await synthesize_report(report_dict)

    claim.fraud_confidence_score = breakdown.final_score
    consistency = next((s for s in breakdown.subscores if s.name == "consistency"), None)
    if consistency and consistency.value is not None:
        claim.consistency_score = consistency.value
    claim.artifact_report = json.dumps(report_dict)
    claim.status = BAND_TO_STATUS[breakdown.routing_band]
    db.commit()

    # Per-level score division on the permanent audit trail (lifecycle tab + PDF)
    from app.agents.audit_logger import log_event
    LEVEL_LABELS = {"metadata": "L1_metadata", "image": "L2_image", "video": "L2_video",
                    "audio": "L2_audio", "text": "L2_text", "consistency": "L3_consistency"}
    score_details = {
        LEVEL_LABELS[s.name]: (round(s.value, 1) if s.value is not None else s.status)
        for s in breakdown.subscores
    }
    score_details.update({
        "base_score": round(breakdown.base_score, 1),
        "final_score": round(breakdown.final_score, 1),
        "routing_band": breakdown.routing_band,
    })
    if breakdown.escalated:
        score_details["escalated_by"] = breakdown.escalation_source
    log_event(db, claim_id, "agent", "fusion_scores_recorded",
              actor_id="fusion_scoring_engine", details=score_details)

    return breakdown.final_score
