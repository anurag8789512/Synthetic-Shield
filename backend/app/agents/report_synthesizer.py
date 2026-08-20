"""
Report Synthesizer: sits between the detection providers (raw scores) and the
dashboard. Uses the Copilot LLM to turn per-modality raw detector output into
a clear human-readable narrative. Falls back silently to the template-based
report when no LLM is configured.
"""
import json

from app.providers.llm_provider import chat, llm_available, LLMUnavailable

SYNTH_PROMPT = """You are an insurance fraud analysis report writer. Given raw deepfake-detection results for a motor insurance claim, write clear plain-English text for a claims officer.

Rules:
- Only describe what the data shows. No speculation, no invented details.
- Reference the actual scores and findings provided.
- Keep each modality explanation to 1-2 sentences.

Respond ONLY with JSON in this exact shape:
{
  "summary": "2-3 sentence overall assessment",
  "recommendation": "1 sentence recommended action",
  "modality_explanations": {"video": "...", "audio": "...", "image": "...", "text": "..."}
}
Include only the modalities present in the input.

Raw detection data:
"""


async def synthesize_report(report: dict) -> dict:
    """Enrich a template artifact report with LLM-written narrative. Returns the
    (possibly updated) report dict; on any failure returns it unchanged."""
    if not llm_available():
        return report

    payload = {
        "fraud_confidence_score": report.get("fraud_confidence_score"),
        "modalities": [
            {
                "modality": m.get("modality"),
                "raw_score": m.get("raw_score"),
                "provider": m.get("provider"),
                "verdict": m.get("verdict"),
                "findings": m.get("findings", []),
            }
            for m in report.get("modality_reports", [])
        ],
    }

    try:
        result = await chat(
            [{"role": "user", "content": SYNTH_PROMPT + json.dumps(payload, indent=1)}],
            temperature=0.1,
        )
        text = (result.get("content") or "").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        narrative = json.loads(text)
    except (LLMUnavailable, json.JSONDecodeError, KeyError) as e:
        print(f"[SYNTHESIZER] LLM narrative failed ({e}) — keeping template report")
        return report

    if narrative.get("summary"):
        report["summary"] = narrative["summary"]
    if narrative.get("recommendation"):
        report["recommendation"] = narrative["recommendation"]
    explanations = narrative.get("modality_explanations") or {}
    for m in report.get("modality_reports", []):
        if m.get("modality") in explanations:
            m["explanation"] = explanations[m["modality"]]
    report["narrative_source"] = "llm"

    print("[SYNTHESIZER] LLM narrative applied to artifact report")
    return report
