"""
Tools available to the Copilot Agent.
Every DB lookup is hard-scoped: WHERE claim_id = :current_claim_id.
"""
import json

import httpx
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim, ClaimMediaAnalysis, Coverage


def get_claim_evidence_summary(claim_id: int, db: DBSession) -> dict:
    """Format the claim's stored detection findings + artifact report. No external calls."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        return {"error": "Claim not found."}

    coverage = db.query(Coverage).filter(Coverage.id == claim.coverage_id).first() if claim.coverage_id else None
    analyses = db.query(ClaimMediaAnalysis).filter(ClaimMediaAnalysis.claim_id == claim_id).all()

    modality_findings = []
    for a in analyses:
        findings = []
        try:
            data = json.loads(a.findings_json) if a.findings_json else {}
            findings = [f.get("detail", str(f)) if isinstance(f, dict) else str(f) for f in data.get("findings", [])]
        except json.JSONDecodeError:
            pass
        modality_findings.append({
            "modality": a.modality,
            "provider": a.provider,
            "raw_score": a.raw_score,
            "findings": findings,
        })

    report = {}
    if claim.artifact_report:
        try:
            report = json.loads(claim.artifact_report)
        except json.JSONDecodeError:
            report = {"raw": claim.artifact_report}

    valuation = {}
    if claim.valuation_report:
        try:
            valuation = json.loads(claim.valuation_report)
        except json.JSONDecodeError:
            valuation = {"raw": claim.valuation_report}

    return {
        "claim_number": claim.claim_number,
        "status": claim.status,
        "coverage_type": coverage.coverage_label if coverage else None,
        "accident_location": claim.accident_location,
        "accident_description": claim.accident_description,
        "fraud_confidence_score": claim.fraud_confidence_score,
        "narrative_similarity_score": claim.narrative_similarity_score,
        "claim_amount_cents": claim.claim_amount_cents,
        "payout_amount_cents": claim.payout_amount_cents,
        "payout_transaction_id": claim.payout_transaction_id,
        "automated_valuation": valuation or None,
        "per_modality_analysis": modality_findings,
        "artifact_report_summary": report.get("summary"),
        "artifact_report_recommendation": report.get("recommendation"),
        "detected_artifacts": report.get("detected_artifacts", []),
    }


def get_fraud_score_breakdown(claim_id: int, db: DBSession) -> dict:
    """Per-level division of the fusion fraud score (Level 1 metadata, Level 2 AI
    manipulation, Level 3 consistency). Stored data only; no external calls."""
    from app.scoring.persistence import ClaimScore

    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        return {"error": "Claim not found."}

    row = (
        db.query(ClaimScore)
        .filter(ClaimScore.claim_id == str(claim.claim_number))
        .order_by(ClaimScore.version.desc())
        .first()
    )
    if not row:
        return {"error": "No fusion score breakdown is recorded for this claim "
                         "(it may have been scored before the fusion engine was introduced)."}

    try:
        breakdown = json.loads(row.breakdown_json)
    except json.JSONDecodeError:
        return {"error": "Stored score breakdown could not be parsed."}

    LEVELS = {
        "metadata": "level_1_metadata_analysis",
        "image": "level_2_ai_manipulation",
        "video": "level_2_ai_manipulation",
        "audio": "level_2_ai_manipulation",
        "text": "level_2_ai_manipulation",
        "consistency": "level_3_consistency_check",
    }
    levels: dict = {"level_1_metadata_analysis": [], "level_2_ai_manipulation": [],
                    "level_3_consistency_check": []}
    weights = breakdown.get("weights_used", {})
    for sub in breakdown.get("subscores", []):
        name = sub.get("name")
        levels[LEVELS.get(name, "level_2_ai_manipulation")].append({
            "signal": name,
            "score": sub.get("value"),
            "status": sub.get("status"),
            "weight_used": weights.get(name),
            "provider": sub.get("provider"),
            "component_scores": sub.get("components") or None,
            "findings": [f.get("human_readable") for f in sub.get("findings", [])],
        })

    return {
        "claim_number": claim.claim_number,
        "score_version": row.version,
        "config_version": row.config_version,
        "levels": levels,
        "base_score": breakdown.get("base_score"),
        "final_score": breakdown.get("final_score"),
        "escalated": breakdown.get("escalated"),
        "escalation_source": breakdown.get("escalation_source"),
        "routing_band": breakdown.get("routing_band"),
        "forced_review_reason": breakdown.get("forced_review_reason"),
        "note": "Scores are 0-100, higher = more fraud-suspicious. Final score is the "
                "weighted fusion of available signals with worst-signal escalation.",
    }


async def search_repair_cost_estimate(part_name: str, vehicle_description: str) -> dict:
    """Live repair-cost lookup: SerpApi search + LLM extraction from snippets."""
    if not settings.SERPAPI_API_KEY:
        return {
            "error": "Repair cost search is unavailable — SERPAPI_API_KEY is not configured.",
            "confidence": "unavailable",
        }

    query = f"{part_name} repair replacement cost {vehicle_description}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://serpapi.com/search",
            params={"engine": "google", "q": query, "num": 6, "api_key": settings.SERPAPI_API_KEY},
        )
        if resp.status_code != 200:
            return {"error": f"Search failed ({resp.status_code}).", "confidence": "unavailable"}
        data = resp.json()

    snippets = []
    for r in (data.get("organic_results") or [])[:6]:
        snippet = r.get("snippet", "")
        if snippet:
            snippets.append({"source": r.get("link", ""), "title": r.get("title", ""), "snippet": snippet})

    if not snippets:
        return {"error": "No search results found for this repair query.", "confidence": "low", "source_snippets": []}

    # LLM extracts a structured estimate from the snippets
    from app.providers.llm_provider import chat, LLMUnavailable

    extraction_prompt = (
        "You are extracting repair cost data from web search snippets. "
        "Find ANY dollar amounts or price ranges mentioned for this repair and produce a best-effort range. "
        "Respond ONLY with JSON: {\"estimated_min_cents\": int|null, \"estimated_max_cents\": int|null, "
        "\"confidence\": \"high\"|\"medium\"|\"low\"}. "
        "Convert dollars to integer cents (e.g. $450 -> 45000). "
        "Return null values ONLY if no snippet mentions any relevant dollar figure at all. "
        "Confidence: high = multiple snippets agree, medium = figures found but scattered, low = weak/single source. "
        f"Query: {query}\n\nSnippets:\n" + json.dumps(snippets, indent=1)
    )
    try:
        result = await chat([{"role": "user", "content": extraction_prompt}], temperature=0.0)
        text = (result.get("content") or "").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        extracted = json.loads(text)
    except (LLMUnavailable, json.JSONDecodeError, KeyError):
        extracted = {"estimated_min_cents": None, "estimated_max_cents": None, "confidence": "low"}

    return {
        "estimated_min_cents": extracted.get("estimated_min_cents"),
        "estimated_max_cents": extracted.get("estimated_max_cents"),
        "confidence": extracted.get("confidence", "low"),
        "source_snippets": snippets,
    }


# Gemini function declarations for the copilot agent
TOOL_DECLARATIONS = [
    {
        "name": "get_claim_evidence_summary",
        "description": "Return this claim's stored detection findings, per-modality analysis scores, and the AI-generated artifact report. Use this to answer any question about the claim's evidence.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_fraud_score_breakdown",
        "description": (
            "Return the division of this claim's fraud score across the three analysis levels: "
            "Level 1 metadata analysis, Level 2 AI-manipulation analysis (image/video/audio/text), "
            "and Level 3 consistency check — with each signal's score, weight, status, component "
            "scores, and findings, plus the base score, final fused score, escalation info, and "
            "routing band. Use this whenever the officer asks how the fraud score was computed, "
            "what each level/check scored, or why the claim was routed the way it was. Works for "
            "every claim regardless of outcome. Stored data only — fast."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search_repair_cost_estimate",
        "description": "Search the web for real-world repair/replacement cost estimates for a damaged vehicle part. Returns an estimated cost range with source snippets and a confidence level.",
        "parameters": {
            "type": "object",
            "properties": {
                "part_name": {"type": "string", "description": "The damaged part, e.g. 'rear bumper', 'driver side mirror'"},
                "vehicle_description": {"type": "string", "description": "Vehicle make/model/year if known, else a generic description like 'mid-size sedan'"},
            },
            "required": ["part_name", "vehicle_description"],
        },
    },
    {
        "name": "run_image_forensics_reanalysis",
        "description": (
            "Run a fresh, deeper multi-specialist vision-LLM investigation of this claim's evidence photo: "
            "AI image manipulation, damage/narrative consistency, real EXIF metadata, a real repair-cost web "
            "search, and real claim-history pattern checks. Much slower than get_claim_evidence_summary — "
            "use it only when the officer explicitly asks for a fresh/deeper look, a second opinion, or "
            "specifically about EXIF/metadata that get_claim_evidence_summary doesn't cover. This is "
            "informational only: it never changes the claim's official fraud score or status."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
]
