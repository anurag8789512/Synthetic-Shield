"""
Claim Valuation Agent.

Runs only for claims the detection pipeline has cleared as genuine (auto_approved —
i.e. the video/image "reality defender" style check found no synthetic evidence).
Reuses the copilot's SerpApi repair-cost tool to check the customer-declared claim
amount against a real-world market estimate for the damaged part, then decides the
payout: the full claim amount if it's at or below the market estimate, otherwise
capped to the estimated part cost.
"""
import json

from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim
from app.agents.copilot_tools import search_repair_cost_estimate
from app.providers.llm_provider import chat, llm_available, LLMUnavailable

# Heuristic fallback (used when no LLM is configured) — longest names first so
# "front bumper" matches before the more generic "bumper".
_KNOWN_PARTS = sorted([
    "front bumper", "rear bumper", "bumper", "windshield", "windscreen",
    "headlight", "headlamp", "taillight", "tail light", "side mirror",
    "wing mirror", "door", "fender", "hood", "bonnet", "trunk", "boot",
    "wheel", "tire", "tyre", "grille", "hubcap", "panel", "roof", "window",
], key=len, reverse=True)

_KNOWN_VEHICLE_TYPES = ["sedan", "suv", "hatchback", "coupe", "truck", "pickup", "van", "motorcycle", "convertible"]


def _heuristic_extract(description: str) -> tuple[str, str]:
    text = (description or "").lower()
    part_name = next((p for p in _KNOWN_PARTS if p in text), "vehicle body panel")
    vehicle_description = next((v for v in _KNOWN_VEHICLE_TYPES if v in text), "passenger vehicle")
    return part_name, vehicle_description


async def extract_damaged_part(description: str) -> tuple[str, str]:
    """Best-effort extraction of (part_name, vehicle_description) from the claim narrative."""
    if not llm_available():
        return _heuristic_extract(description)

    prompt = (
        "Extract the single most likely damaged vehicle part and a short vehicle "
        "description from this accident report. Respond ONLY with JSON: "
        '{"part_name": string, "vehicle_description": string}. '
        "If unclear, guess reasonably (e.g. part_name='vehicle body panel', "
        "vehicle_description='passenger vehicle').\n\n"
        f"Accident description: {description}"
    )
    try:
        result = await chat([{"role": "user", "content": prompt}], temperature=0.0)
        text = (result.get("content") or "").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        data = json.loads(text)
        part_name = (data.get("part_name") or "").strip() or "vehicle body panel"
        vehicle_description = (data.get("vehicle_description") or "").strip() or "passenger vehicle"
        return part_name, vehicle_description
    except (LLMUnavailable, json.JSONDecodeError, KeyError, AttributeError):
        return _heuristic_extract(description)


async def evaluate_claim_valuation(claim: Claim, db: DBSession) -> dict:
    """
    Compare the customer-declared claim amount against a live market estimate for the
    damaged part and decide the payout. Writes the reasoning onto claim.valuation_report
    as JSON (caller commits). Returns the same report dict, including approved_amount_cents.
    """
    claim_amount_cents = claim.claim_amount_cents

    if claim_amount_cents is None:
        report = {
            "method": "no_claim_amount_provided",
            "reasoning": "No claim amount was submitted with this claim; falling back to the standard payout.",
            "approved_amount_cents": settings.MOCK_PAYOUT_AMOUNT_CENTS,
        }
        claim.valuation_report = json.dumps(report)
        return report

    part_name, vehicle_description = await extract_damaged_part(claim.accident_description or "")
    cost_estimate = await search_repair_cost_estimate(part_name, vehicle_description)

    est_min = cost_estimate.get("estimated_min_cents")
    est_max = cost_estimate.get("estimated_max_cents")
    if est_min is not None and est_max is not None:
        part_cost_cents = round((est_min + est_max) / 2)
    elif est_min is not None:
        part_cost_cents = est_min
    elif est_max is not None:
        part_cost_cents = est_max
    else:
        part_cost_cents = None

    if part_cost_cents is None:
        approved_amount_cents = claim_amount_cents
        method = "cost_lookup_unavailable"
        reasoning = (
            f"Could not find a reliable market cost estimate for the {part_name}; "
            "approving the full declared claim amount."
        )
    elif claim_amount_cents > part_cost_cents:
        approved_amount_cents = part_cost_cents
        method = "capped_to_part_cost"
        reasoning = (
            f"Declared claim amount (${claim_amount_cents / 100:,.2f}) exceeds the estimated market "
            f"cost of the {part_name} (${part_cost_cents / 100:,.2f}); approving only the part cost."
        )
    else:
        approved_amount_cents = claim_amount_cents
        method = "approved_full_claim_amount"
        reasoning = (
            f"Declared claim amount (${claim_amount_cents / 100:,.2f}) is within the estimated market "
            f"cost of the {part_name} (${part_cost_cents / 100:,.2f}); approving the full declared amount."
        )

    report = {
        "method": method,
        "reasoning": reasoning,
        "damaged_part": part_name,
        "vehicle_description": vehicle_description,
        "claim_amount_cents": claim_amount_cents,
        "estimated_part_cost_min_cents": est_min,
        "estimated_part_cost_max_cents": est_max,
        "estimated_part_cost_cents": part_cost_cents,
        "cost_confidence": cost_estimate.get("confidence"),
        "source_snippets": cost_estimate.get("source_snippets", []),
        "approved_amount_cents": approved_amount_cents,
    }
    claim.valuation_report = json.dumps(report)
    return report
