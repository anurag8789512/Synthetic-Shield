"""
Detection Agent: runs per-modality analysis, aggregates scores, produces artifact_report.
Providers are selected per modality via env config; real providers fall back to
mock automatically if the vendor call fails, so the pipeline never stalls.
"""
import json
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim, ClaimMediaAnalysis
from app.providers.detection import mock_providers, reality_defender, resemble_ai


async def _run_provider(provider_name: str, kind: str, *args) -> tuple[str, dict]:
    """Run the configured provider for a modality. Returns (provider_used, result)."""
    if provider_name == "reality_defender" and settings.REALITY_DEFENDER_API_KEY:
        try:
            fn = getattr(reality_defender, f"analyze_{kind}")
            result = await fn(*args)
            print(f"[DETECTION] reality_defender {kind}: score={result['raw_score']} status={result.get('vendor_status')}")
            return "reality_defender", result
        except Exception as e:
            print(f"[DETECTION] reality_defender {kind} failed ({e}) — falling back to mock")
    if provider_name == "resemble_ai" and settings.RESEMBLE_AI_API_KEY:
        try:
            fn = getattr(resemble_ai, f"analyze_{kind}", None)
            if fn is None:
                raise AttributeError(f"resemble_ai has no analyze_{kind}")
            result = await fn(*args)
            return "resemble_ai", result
        except Exception as e:
            print(f"[DETECTION] resemble_ai {kind} failed ({e}) — falling back to mock")
    fn = getattr(mock_providers, f"analyze_{kind}")
    return "mock", await fn(*args)


def _media_bytes(claim_number: str, url: str | None) -> tuple[str, bytes]:
    """Resolve a media URL to (filename, file bytes) from the local media store."""
    filename = url.split("/")[-1] if url else "unknown"
    media_path = Path("app/media_store") / claim_number / filename
    content = media_path.read_bytes() if media_path.exists() else filename.encode()
    return filename, content


async def run_detection(claim_id: int, db: DBSession) -> float:
    """Run all detection analyses for a claim and return aggregated fraud score."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        return 0.0

    results = []

    # Video analysis
    if claim.video_url:
        filename, content = _media_bytes(claim.claim_number, claim.video_url)
        provider, video_result = await _run_provider(settings.VIDEO_DETECTION_PROVIDER, "video", filename, content)
        db.add(ClaimMediaAnalysis(
            claim_id=claim_id,
            modality="video",
            provider=provider,
            raw_score=video_result["raw_score"],
            findings_json=json.dumps(video_result),
        ))
        results.append(("video", video_result["raw_score"], 0.35))

    # Audio analysis
    if claim.audio_url:
        filename, content = _media_bytes(claim.claim_number, claim.audio_url)
        provider, audio_result = await _run_provider(settings.AUDIO_DETECTION_PROVIDER, "audio", filename, content)
        db.add(ClaimMediaAnalysis(
            claim_id=claim_id,
            modality="audio",
            provider=provider,
            raw_score=audio_result["raw_score"],
            findings_json=json.dumps(audio_result),
        ))
        results.append(("audio", audio_result["raw_score"], 0.30))

    # Image analysis (from dedicated image file)
    if claim.image_url:
        filename, content = _media_bytes(claim.claim_number, claim.image_url)
        provider, image_result = await _run_provider(settings.IMAGE_DETECTION_PROVIDER, "image", filename, content)
        db.add(ClaimMediaAnalysis(
            claim_id=claim_id,
            modality="image",
            provider=provider,
            raw_score=image_result["raw_score"],
            findings_json=json.dumps(image_result),
        ))
        results.append(("image", image_result["raw_score"], 0.20))

    # Text analysis (claim narrative)
    if claim.accident_description:
        provider, text_result = await _run_provider(settings.TEXT_DETECTION_PROVIDER, "text", claim.accident_description)
        db.add(ClaimMediaAnalysis(
            claim_id=claim_id,
            modality="text",
            provider=provider,
            raw_score=text_result["raw_score"],
            findings_json=json.dumps(text_result),
        ))
        results.append(("text", text_result["raw_score"], 0.15))

    # Weighted aggregation
    if not results:
        aggregated = 0.0
    else:
        total_weight = sum(w for _, _, w in results)
        aggregated = sum(score * weight for _, score, weight in results) / total_weight

    aggregated = round(aggregated, 1)

    # Build rich artifact report with per-modality breakdowns
    modality_reports = []
    all_findings = []
    for modality, score, weight in results:
        analysis = db.query(ClaimMediaAnalysis).filter(
            ClaimMediaAnalysis.claim_id == claim_id,
            ClaimMediaAnalysis.modality == modality,
        ).first()

        findings = []
        if analysis and analysis.findings_json:
            data = json.loads(analysis.findings_json)
            findings = data.get("findings", [])
            for f in findings:
                all_findings.append(f["detail"])

        severity = "low" if score < 30 else "medium" if score <= 70 else "high"
        verdict = "authentic" if score < 15 else "inconclusive" if score <= 85 else "synthetic"

        explanation_parts = []
        if modality == "video":
            if score > 85:
                explanation_parts.append(f"Video analysis detected frame-level artifacts consistent with AI-generated imagery (confidence: {score:.0f}%).")
            elif score > 50:
                explanation_parts.append(f"Video shows minor inconsistencies that warrant manual inspection (score: {score:.0f}%).")
            else:
                explanation_parts.append(f"No significant synthetic artifacts detected in video (score: {score:.0f}%).")
        elif modality == "audio":
            if score > 85:
                explanation_parts.append(f"Voice biometric analysis indicates synthetic speech patterns — likely voice clone (confidence: {score:.0f}%).")
            elif score > 50:
                explanation_parts.append(f"Audio shows frequency anomalies that may indicate manipulation (score: {score:.0f}%).")
            else:
                explanation_parts.append(f"Voice analysis consistent with natural human speech (score: {score:.0f}%).")
        elif modality == "image":
            if score > 85:
                explanation_parts.append(f"Image contains pixel-level GAN artifacts consistent with AI generation (confidence: {score:.0f}%).")
            elif score > 50:
                explanation_parts.append(f"Image shows lighting or texture inconsistencies (score: {score:.0f}%).")
            else:
                explanation_parts.append(f"Image appears authentic with no detectable manipulation (score: {score:.0f}%).")
        elif modality == "text":
            if score > 85:
                explanation_parts.append(f"Narrative exhibits uniform perplexity patterns typical of AI-generated text (confidence: {score:.0f}%).")
            elif score > 50:
                explanation_parts.append(f"Text shows some statistical anomalies but is inconclusive (score: {score:.0f}%).")
            else:
                explanation_parts.append(f"Narrative appears to be human-written (score: {score:.0f}%).")

        for f in findings:
            explanation_parts.append(f"• {f.get('detail', '')}")

        modality_reports.append({
            "modality": modality,
            "raw_score": score,
            "severity": severity,
            "verdict": verdict,
            "weight": weight,
            "provider": analysis.provider if analysis else "mock",
            "explanation": " ".join(explanation_parts) if explanation_parts else "No findings.",
            "findings": [f.get("detail", "") for f in findings],
            "timestamps": [f.get("timestamp_or_location") for f in findings if f.get("timestamp_or_location")],
        })

    if aggregated < 15:
        recommendation = "Auto-approve. No significant synthetic artifacts detected across any modality."
        summary = f"All evidence analyzed across {len(results)} modalities. No synthetic indicators found. Claim is safe for automatic approval."
    elif aggregated <= 85:
        flagged = [r["modality"] for r in modality_reports if r["severity"] in ("medium", "high")]
        recommendation = "Route to moderator for manual review."
        summary = f"Mixed signals detected. {', '.join(f.capitalize() for f in flagged) if flagged else 'Some'} evidence requires human review before a decision can be made."
    else:
        high_signals = [r["modality"] for r in modality_reports if r["severity"] == "high"]
        recommendation = "Route to SIU investigator for immediate review."
        summary = f"High-confidence synthetic indicators found in {', '.join(f.capitalize() for f in high_signals) if high_signals else 'multiple modalities'}. This claim shows strong evidence of fabricated evidence."

    report_dict = {
        "fraud_confidence_score": aggregated,
        "summary": summary,
        "recommendation": recommendation,
        "detected_artifacts": all_findings,
        "modality_reports": modality_reports,
        "total_modalities_analyzed": len(results),
        "flagged_modalities": [r["modality"] for r in modality_reports if r["severity"] != "low"],
    }

    # LLM narrative layer: turn raw detector scores into officer-readable text
    from app.agents.report_synthesizer import synthesize_report
    report_dict = await synthesize_report(report_dict)

    artifact_report = json.dumps(report_dict)

    # Update claim
    claim.fraud_confidence_score = aggregated
    claim.artifact_report = artifact_report

    # Adjudication: set status based on thresholds
    if aggregated < settings.AUTO_APPROVE_BELOW:
        claim.status = "auto_approved"
    elif aggregated > settings.SIU_FLAG_ABOVE:
        claim.status = "siu_investigation"
    else:
        claim.status = "moderator_review"

    db.commit()
    return aggregated
