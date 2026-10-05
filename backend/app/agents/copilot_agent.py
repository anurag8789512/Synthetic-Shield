"""
Copilot Agent: answers officer questions about a specific claim.
LLM-backed (Gemini via COPILOT_LLM_PROVIDER, swappable) with tool calling;
falls back to a rule-based responder when no LLM is configured.
Strictly grounded: every DB lookup is scoped WHERE claim_id = :current_claim_id.
Never surfaces data from other claims. Says "I don't have that information"
rather than speculating beyond what was actually analyzed.
"""
import json
from sqlalchemy.orm import Session as DBSession

from app.models import Claim, ClaimMediaAnalysis, CopilotMessage
from app.providers.llm_provider import chat, llm_available, LLMUnavailable
from app.agents.copilot_tools import (
    get_claim_evidence_summary, get_fraud_score_breakdown, search_repair_cost_estimate,
    TOOL_DECLARATIONS,
)
from app.agents.image_forensics_agent import run_image_forensics_reanalysis
from app.agents.audit_logger import log_event

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """You are the SyntheticShield Claims Copilot, assisting an insurance fraud investigation officer with ONE specific claim ({claim_number}).

HARD GROUNDING RULES (non-negotiable):
1. Answer ONLY from: (a) this claim's stored data returned by get_claim_evidence_summary, (b) the per-level score division returned by get_fraud_score_breakdown, (c) live results returned by search_repair_cost_estimate, (d) a fresh investigation returned by run_image_forensics_reanalysis. Never speculate beyond what these actually return.
2. If asked about anything outside this claim's analyzed evidence (claimant credit history, other claims, personal data, anything not in the tools' output), reply that this information is not available to you. Do not guess or infer.
3. You have NO access to other claims beyond what run_image_forensics_reanalysis's historical-pattern check explicitly returns for THIS claim (same policyholder / similar amount). If asked to compare more broadly, state this data isolation restriction plainly.
4. When you use search_repair_cost_estimate, report only what it returned, cite the source links, and if confidence is "low" say so plainly instead of presenting numbers as reliable.

SCORE DIVISION QUESTIONS (get_fraud_score_breakdown):
- When the officer asks how the score was computed, what each level found, or about any of the three levels (metadata analysis, AI manipulation analysis, consistency check), call get_fraud_score_breakdown and present the division level by level: Level 1 Metadata, Level 2 AI Manipulation (image, video, audio, text), Level 3 Consistency.
- Report each signal's score out of 100 with its weight, flag unavailable/not-applicable signals plainly, then give the base score, the final score, whether worst-signal escalation fired and from which signal, and the routing band. This works for every claim, fraudulent or not.

DEEPER REANALYSIS (run_image_forensics_reanalysis):
- This tool is slow (multiple LLM calls) and is a fresh second opinion, separate from the fraud score computed at submission — it never changes the claim's official status or fraud_confidence_score. Only call it when the officer explicitly asks for a fresh/deeper look, a second opinion on the photo, or specifically about EXIF/metadata that get_claim_evidence_summary doesn't cover — not on every question.
- Its result has per_parameter scores/observations, a narrative_summary, and the real EXIF/repair-cost/history data it used. When you report it, lead with narrative_summary, then pull out only the 1-3 parameters most relevant to what was asked. Make clear this is a supplementary reanalysis, not a new official score.
- If it returns an "error" (no photo on file, or no LLM configured), say so plainly instead of retrying.

PRICE & CLAIM AMOUNT QUESTIONS:
- get_claim_evidence_summary returns claim_amount_cents (what the customer declared they're claiming) and automated_valuation (present only if the auto-approval pipeline already ran a cost check — it contains the damaged part, the market cost estimate, and which amount was approved and why).
- If automated_valuation is already present, use it directly to answer questions about whether the claim amount was legitimate — don't re-run the search unless the officer explicitly asks for a fresh check.
- If automated_valuation is absent (this claim went to moderator/SIU review instead of auto-approval) and the officer asks whether the claim amount looks reasonable, or asks about repair/replacement cost for the damaged part, call search_repair_cost_estimate with the damaged part (inferred from the accident description) and the vehicle details, then compare the result against claim_amount_cents yourself: state plainly whether the declared amount is at/below the market estimate (reasonable) or above it (inflated), and by how much.
- The claim's own payout amount (if paid) also comes from get_claim_evidence_summary — compare it against the market range and state clearly whether it falls inside or outside.
- Always show money as dollars (e.g. $1,250.00), never raw cents.

HOW TO WRITE YOUR ANSWERS (style rules):
- Write like a helpful colleague, not a database. Plain conversational English first, then supporting detail.
- Start with a one-sentence direct answer to the question. Then add short supporting bullets if needed.
- Never dump raw JSON, field names (like "raw_score" or "findings_json"), or internal status codes. Translate everything: "fraud_confidence_score: 69.3" becomes "an overall fraud risk of 69%".
- Use **bold** for key numbers and verdicts. Use short bullet lists, never long tables unless comparing modalities.
- Round percentages to whole numbers. Keep the whole answer under ~150 words unless the officer asks for full detail."""


def _build_context(claim: Claim, analyses: list[ClaimMediaAnalysis]) -> str:
    """Build a context string from the claim's actual detection data."""
    parts = [f"Claim: {claim.claim_number}", f"Status: {claim.status}"]
    parts.append(f"Location: {claim.accident_location}")
    parts.append(f"Description: {claim.accident_description}")
    parts.append(f"Fraud Score: {claim.fraud_confidence_score}%")

    if claim.claim_amount_cents is not None:
        parts.append(f"Claim Amount: ${claim.claim_amount_cents / 100:,.2f}")

    if claim.valuation_report:
        try:
            valuation = json.loads(claim.valuation_report)
            parts.append(f"Valuation: {valuation.get('reasoning', '')}")
        except json.JSONDecodeError:
            pass

    if claim.artifact_report:
        try:
            report = json.loads(claim.artifact_report)
            parts.append(f"Summary: {report.get('summary', '')}")
            parts.append(f"Recommendation: {report.get('recommendation', '')}")
            for mr in report.get("modality_reports", []):
                parts.append(f"\n[{mr['modality'].upper()}] Score: {mr['raw_score']}% | Verdict: {mr['verdict']} | Severity: {mr['severity']}")
                parts.append(f"  Explanation: {mr['explanation']}")
                for f in mr.get("findings", []):
                    parts.append(f"  Finding: {f}")
                for t in mr.get("timestamps", []):
                    parts.append(f"  Location/Time: {t}")
        except json.JSONDecodeError:
            parts.append(f"Artifact Report (raw): {claim.artifact_report}")

    for a in analyses:
        if a.findings_json:
            try:
                data = json.loads(a.findings_json)
                for f in data.get("findings", []):
                    detail = f.get("detail", "") if isinstance(f, dict) else str(f)
                    ts = f.get("timestamp_or_location", "") if isinstance(f, dict) else ""
                    parts.append(f"[{a.modality}] Raw finding: {detail}" + (f" at {ts}" if ts else ""))
            except json.JSONDecodeError:
                pass

    return "\n".join(parts)


def _match_question(question: str, context: str) -> str:
    """Generate a grounded response based on the question and available data."""
    q = question.lower().strip()

    # Parse context for quick access
    lines = context.split("\n")
    modality_data = {}
    current_modality = None
    for line in lines:
        for mod in ["video", "audio", "image", "text"]:
            if line.startswith(f"[{mod.upper()}]"):
                current_modality = mod
                if mod not in modality_data:
                    modality_data[mod] = []
                modality_data[mod].append(line)

    fraud_score = ""
    summary = ""
    recommendation = ""
    claim_amount_line = ""
    valuation_line = ""
    for line in lines:
        if line.startswith("Fraud Score:"):
            fraud_score = line
        elif line.startswith("Summary:"):
            summary = line.replace("Summary: ", "")
        elif line.startswith("Recommendation:"):
            recommendation = line.replace("Recommendation: ", "")
        elif line.startswith("Claim Amount:"):
            claim_amount_line = line
        elif line.startswith("Valuation:"):
            valuation_line = line.replace("Valuation: ", "")

    # Question matching
    if any(w in q for w in ["claim amount", "legitimate", "reasonable", "repair cost", "part cost", "overcharg", "inflated"]):
        if valuation_line:
            return f"{claim_amount_line}\n\n{valuation_line}"
        if claim_amount_line:
            return (
                f"{claim_amount_line}\n\nThis claim hasn't gone through the automated cost check "
                "(that only runs on auto-approved claims). Ask me to look up the repair cost for the "
                "damaged part and I can search the web for a market estimate to compare against."
            )
        return "No claim amount was recorded for this claim."

    if any(w in q for w in ["why", "flag", "reason", "suspicious"]):
        response = f"This claim was flagged because: {summary}\n\n"
        for mod, findings in modality_data.items():
            if findings:
                response += f"**{mod.capitalize()}:**\n"
                for f in findings:
                    response += f"  {f}\n"
        response += f"\n{recommendation}"
        return response

    if any(w in q for w in ["audio", "voice", "sound", "speech"]):
        if "audio" in modality_data:
            return "**Audio Analysis:**\n" + "\n".join(modality_data["audio"])
        return "Audio analysis did not detect significant anomalies for this claim."

    if any(w in q for w in ["video", "footage", "dashcam", "frame"]):
        if "video" in modality_data:
            return "**Video Analysis:**\n" + "\n".join(modality_data["video"])
        return "Video analysis did not detect significant anomalies for this claim."

    if any(w in q for w in ["image", "photo", "picture", "pixel"]):
        if "image" in modality_data:
            return "**Image Analysis:**\n" + "\n".join(modality_data["image"])
        return "Image analysis did not detect significant anomalies for this claim."

    if any(w in q for w in ["text", "narrative", "description", "written"]):
        if "text" in modality_data:
            return "**Text/Narrative Analysis:**\n" + "\n".join(modality_data["text"])
        return "Text analysis did not detect significant anomalies in the claim narrative."

    if any(w in q for w in ["score", "confidence", "how bad", "how high"]):
        return f"{fraud_score}\n\n{summary}\n\n{recommendation}"

    if any(w in q for w in ["evidence", "most suspicious", "strongest signal", "worst"]):
        highest_mod = ""
        highest_score = 0
        for line in lines:
            for mod in ["VIDEO", "AUDIO", "IMAGE", "TEXT"]:
                if line.startswith(f"[{mod}]") and "Score:" in line:
                    try:
                        s = float(line.split("Score:")[1].split("%")[0].strip())
                        if s > highest_score:
                            highest_score = s
                            highest_mod = mod.lower()
                    except ValueError:
                        pass
        if highest_mod and highest_mod in modality_data:
            return f"The strongest fraud signal comes from **{highest_mod}** analysis (score: {highest_score}%):\n\n" + "\n".join(modality_data[highest_mod])
        return "I don't have enough modality-specific data to determine the strongest signal."

    if any(w in q for w in ["recommend", "should", "approve", "reject", "action"]):
        return f"Based on the analysis:\n\n{recommendation}\n\n{fraud_score}\n{summary}"

    if any(w in q for w in ["compare", "similar", "other claim", "pattern"]):
        return "I can only analyze evidence from this specific claim. I don't have access to other claims' data for comparison. This is a hard data isolation requirement — I cannot surface information from any other claim."

    if any(w in q for w in ["exif", "metadata"]):
        exif_findings = [l for l in lines if "exif" in l.lower() or "metadata" in l.lower()]
        if exif_findings:
            return "**EXIF/Metadata findings:**\n" + "\n".join(exif_findings)
        return "No specific EXIF or metadata anomalies were detected for this claim."

    if any(w in q for w in ["summary", "overview", "tell me about", "what happened"]):
        return f"**Claim Overview:**\n\n{summary}\n\n{fraud_score}\n\n{recommendation}"

    # Default: provide overview grounded in actual data
    return f"Based on the analysis of {claim.claim_number}:\n\n{summary}\n\n{fraud_score}\n\n{recommendation}\n\nAsk me about specific modalities (video, audio, image, text), the fraud score, evidence details, or what action is recommended."


async def _run_llm_agent(claim: Claim, officer_id: int, message: str, db: DBSession) -> str:
    """LLM path: conversation history + tool-calling loop, all scoped to this claim."""
    # Conversation memory: prior messages for THIS claim only
    history = (
        db.query(CopilotMessage)
        .filter(CopilotMessage.claim_id == claim.id)
        .order_by(CopilotMessage.created_at.asc())
        .all()
    )
    messages: list[dict] = [
        {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
        for m in history[-20:]  # cap context length
    ]
    messages.append({"role": "user", "content": message})

    system = SYSTEM_PROMPT.format(claim_number=claim.claim_number)

    for _ in range(MAX_TOOL_ROUNDS):
        result = await chat(messages, system=system, tools=TOOL_DECLARATIONS)

        tool_call = result.get("tool_call")
        if not tool_call:
            return result.get("content") or "I couldn't generate a response for that question."

        name, args = tool_call["name"], tool_call["args"]

        # Execute the tool — claim_id always comes from the request scope, never the LLM
        if name == "get_claim_evidence_summary":
            tool_result = get_claim_evidence_summary(claim.id, db)
        elif name == "get_fraud_score_breakdown":
            tool_result = get_fraud_score_breakdown(claim.id, db)
        elif name == "search_repair_cost_estimate":
            tool_result = await search_repair_cost_estimate(
                args.get("part_name", ""), args.get("vehicle_description", "")
            )
        elif name == "run_image_forensics_reanalysis":
            tool_result = await run_image_forensics_reanalysis(claim, db)
        else:
            tool_result = {"error": f"Unknown tool: {name}"}

        # Audit every tool call so each answer's evidence is on record
        log_event(db, claim.id, "agent", "copilot_tool_call", actor_id="copilot_agent", details={
            "tool": name,
            "args": args,
            "officer_id": officer_id,
            "result_keys": list(tool_result.keys()) if isinstance(tool_result, dict) else [],
        })

        messages.append({"role": "assistant", "tool_call": tool_call})
        messages.append({"role": "tool", "name": name, "result": tool_result})

    return "I hit the tool-call limit for this question. Please ask a more specific question."


async def copilot_respond(claim_id: int, officer_id: int, message: str, db: DBSession) -> str:
    """Process an officer's question and return a grounded response."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        return "Claim not found."

    # Store officer message
    db.add(CopilotMessage(
        claim_id=claim_id,
        officer_id=officer_id,
        role="officer",
        content=message,
    ))
    db.commit()

    response = None
    if llm_available():
        try:
            response = await _run_llm_agent(claim, officer_id, message, db)
        except LLMUnavailable as e:
            print(f"[COPILOT] LLM failed ({e}) — falling back to rule-based responder")

    if response is None:
        analyses = db.query(ClaimMediaAnalysis).filter(ClaimMediaAnalysis.claim_id == claim_id).all()
        context = _build_context(claim, analyses)
        response = _match_question(message, context)

    # Store AI response
    db.add(CopilotMessage(
        claim_id=claim_id,
        officer_id=officer_id,
        role="assistant",
        content=response,
    ))
    db.commit()
    return response
