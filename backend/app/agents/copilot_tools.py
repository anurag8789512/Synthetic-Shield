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

    return {
        "claim_number": claim.claim_number,
        "status": claim.status,
        "coverage_type": coverage.coverage_label if coverage else None,
        "accident_location": claim.accident_location,
        "accident_description": claim.accident_description,
        "fraud_confidence_score": claim.fraud_confidence_score,
        "narrative_similarity_score": claim.narrative_similarity_score,
        "payout_amount_cents": claim.payout_amount_cents,
        "payout_transaction_id": claim.payout_transaction_id,
        "per_modality_analysis": modality_findings,
        "artifact_report_summary": report.get("summary"),
        "artifact_report_recommendation": report.get("recommendation"),
        "detected_artifacts": report.get("detected_artifacts", []),
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
]
