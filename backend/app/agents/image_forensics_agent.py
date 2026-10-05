"""
Image Forensics Investigation Agent.

Runs ONLY on explicit officer request, as a Copilot tool call (see
copilot_tools.TOOL_DECLARATIONS -> run_image_forensics_reanalysis). It is a
deeper, slower second opinion than the deterministic detection_agent pipeline
that already ran at submission: five specialists each score a distinct slice
of the evidence using real inputs (the claim photo itself, real EXIF data,
a real SerpApi repair-cost search, and real claim-history query results),
then a Supervisor synthesizes their findings into one narrative.

This agent never writes to claim.status or claim.fraud_confidence_score —
per the project's adjudication design, that routing decision stays
deterministic (see instruction/SyntheticShield_Backend_Spec.md, Section 6).
It only returns information for the officer to read in chat.
"""
import io
import json
import mimetypes
from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS
from sqlalchemy.orm import Session as DBSession

from app.models import Claim
from app.providers.llm_provider import chat, llm_available, LLMUnavailable
from app.agents.copilot_tools import search_repair_cost_estimate
from app.agents.valuation_agent import extract_damaged_part
from app.agents.forensics_prompts import (
    IMAGE_FORENSICS_SYSTEM_PROMPT,
    DAMAGE_NARRATIVE_SYSTEM_PROMPT,
    METADATA_PROVENANCE_SYSTEM_PROMPT,
    REPAIR_COST_SYSTEM_PROMPT,
    HISTORICAL_PATTERN_SYSTEM_PROMPT,
    SUPERVISOR_SYNTHESIS_PROMPT,
    SPECIALIST_PARAMS,
    build_user_prompt,
)

import asyncio


def _load_claim_image(claim: Claim) -> tuple[str, bytes] | None:
    """Read the claim's evidence photo off local media storage, if any."""
    if not claim.image_url:
        return None
    filename = claim.image_url.split("/")[-1]
    path = Path("app/media_store") / claim.claim_number / filename
    if not path.exists():
        return None
    mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    return mime_type, path.read_bytes()


def _extract_exif(content: bytes) -> dict:
    """Best-effort real EXIF extraction. Returns {} if the file has none
    (very common — most phones/apps strip it on save/share)."""
    try:
        with Image.open(io.BytesIO(content)) as img:
            raw = img.getexif()
            if not raw:
                return {}
            return {
                str(TAGS.get(tag_id, tag_id)): str(value)
                for tag_id, value in raw.items()
                if not isinstance(value, bytes)
            }
    except Exception:
        return {}


def _historical_pattern_records(claim: Claim, db: DBSession) -> list[dict]:
    """Real query results: this policyholder's other claims, plus any other
    claims with a similar claimed amount."""
    records = []

    prior = (
        db.query(Claim)
        .filter(Claim.user_id == claim.user_id, Claim.id != claim.id)
        .all()
    )
    for c in prior:
        records.append({
            "claim_number": c.claim_number,
            "status": c.status,
            "claim_amount_cents": c.claim_amount_cents,
            "relation": "same_policyholder",
        })

    if claim.claim_amount_cents:
        lo, hi = claim.claim_amount_cents * 0.9, claim.claim_amount_cents * 1.1
        similar = (
            db.query(Claim)
            .filter(
                Claim.id != claim.id,
                Claim.user_id != claim.user_id,
                Claim.claim_amount_cents >= lo,
                Claim.claim_amount_cents <= hi,
            )
            .limit(10)
            .all()
        )
        for c in similar:
            records.append({
                "claim_number": c.claim_number,
                "status": c.status,
                "claim_amount_cents": c.claim_amount_cents,
                "relation": "similar_claimed_amount",
            })

    return records


def _unavailable_result(params: list[str], reason: str) -> dict:
    return {p: {"observations": [reason], "score": None, "confidence": "unavailable"} for p in params}


def _parse_specialist_response(text: str | None, params: list[str]) -> dict:
    if not text:
        return _unavailable_result(params, "Specialist returned no content.")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return _unavailable_result(params, "Specialist response could not be parsed as JSON.")
    return {p: parsed[p] for p in params if p in parsed} or _unavailable_result(
        params, "Specialist response did not include the requested parameters."
    )


async def _run_specialist(
    system_prompt: str,
    params: list[str],
    narrative: str,
    claimed_amount: float,
    currency: str,
    extra_context: str = "",
    image: tuple[str, bytes] | None = None,
) -> dict:
    user_prompt = build_user_prompt(params, narrative, claimed_amount, currency, extra_context)
    try:
        result = await chat(
            [{"role": "user", "content": user_prompt}],
            system=system_prompt,
            temperature=0.2,
            images=[image] if image else None,
        )
    except LLMUnavailable as e:
        return _unavailable_result(params, f"Specialist call failed: {e}")
    return _parse_specialist_response(result.get("content"), params)


async def run_image_forensics_reanalysis(claim: Claim, db: DBSession) -> dict:
    """Entry point called by the Copilot Agent's run_image_forensics_reanalysis tool."""
    if not llm_available():
        return {
            "error": "Image forensics reanalysis requires an LLM provider "
                     "(Mistral or Gemini) to be configured; none is available right now.",
        }

    image = _load_claim_image(claim)
    if image is None:
        return {"error": "No evidence photo is on file for this claim, so a fresh visual reanalysis can't be run."}

    narrative = claim.accident_description or ""
    claimed_amount = (claim.claim_amount_cents or 0) / 100
    currency = "USD"

    exif_data = _extract_exif(image[1])
    part_name, vehicle_description = await extract_damaged_part(narrative)
    cost_estimate = await search_repair_cost_estimate(part_name, vehicle_description)
    history_records = _historical_pattern_records(claim, db)

    transcript_context = f'Voice statement transcript: "{claim.transcript_text}"' if claim.transcript_text else ""

    specialist_calls = [
        _run_specialist(
            IMAGE_FORENSICS_SYSTEM_PROMPT, SPECIALIST_PARAMS["image_forensics"],
            narrative, claimed_amount, currency, image=image,
        ),
        _run_specialist(
            DAMAGE_NARRATIVE_SYSTEM_PROMPT, SPECIALIST_PARAMS["damage_narrative"],
            narrative, claimed_amount, currency, extra_context=transcript_context, image=image,
        ),
        _run_specialist(
            METADATA_PROVENANCE_SYSTEM_PROMPT, SPECIALIST_PARAMS["metadata_provenance"],
            narrative, claimed_amount, currency,
            extra_context=f"Real EXIF metadata extracted from the photo file:\n{json.dumps(exif_data, indent=1) or '{} (no EXIF block present)'}",
        ),
        _run_specialist(
            REPAIR_COST_SYSTEM_PROMPT, SPECIALIST_PARAMS["repair_cost"],
            narrative, claimed_amount, currency,
            extra_context=f"Real web search results for '{part_name}' on a {vehicle_description}:\n{json.dumps(cost_estimate, indent=1)}",
        ),
        _run_specialist(
            HISTORICAL_PATTERN_SYSTEM_PROMPT, SPECIALIST_PARAMS["historical_pattern"],
            narrative, claimed_amount, currency,
            extra_context=f"Real claim-history query results:\n{json.dumps(history_records, indent=1) or '[] (no related claims found)'}",
        ),
    ]
    specialist_results = await asyncio.gather(*specialist_calls)

    per_parameter: dict = {}
    for result in specialist_results:
        per_parameter.update(result)

    try:
        synthesis = await chat(
            [{"role": "user", "content": json.dumps(per_parameter, indent=1)}],
            system=SUPERVISOR_SYNTHESIS_PROMPT,
            temperature=0.2,
        )
        narrative_summary = synthesis.get("content") or "Synthesis unavailable."
    except LLMUnavailable as e:
        narrative_summary = f"Per-parameter findings are below; narrative synthesis failed: {e}"

    return {
        "per_parameter": per_parameter,
        "narrative_summary": narrative_summary,
        "damaged_part": part_name,
        "vehicle_description": vehicle_description,
        "repair_cost_search": cost_estimate,
        "historical_records": history_records,
        "exif_data": exif_data,
        "note": "Supplementary reanalysis triggered by officer request — does not change the claim's official fraud score or status.",
    }
