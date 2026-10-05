"""One-off DEMO backfill: give every claim a complete 6-signal fusion breakdown.

- Claims already fusion-scored: seed mock audio/text where unavailable, re-fuse.
- Legacy claims (scored by the old pipeline, no breakdown): build a breakdown from
  their existing per-modality detection scores + deterministic seeded values for
  metadata/consistency, aligned with their recorded fraud score.
Claim statuses are intentionally NOT changed (no re-adjudication).

Run: python rescore_audio_text.py   (from backend/, venv active)
"""
import asyncio
import hashlib
import json

from app.database import SessionLocal
from app.models import Claim, ClaimMediaAnalysis
from app.scoring.config import get_config
from app.scoring.fusion import fuse
from app.scoring.models import ScoreBreakdown, SubScore
from app.scoring.orchestrator import _media_path, combine_text_scores
from app.scoring.persistence import ClaimScore, next_version, save_breakdown
from app.scoring.level2_manipulation.providers.base import MockDetectorProvider
from app.agents.scoring_adapter import build_artifact_report


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _seeded_jitter(key: str, lo: float, hi: float) -> float:
    h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    return lo + (h % 1000) / 1000.0 * (hi - lo)


async def _mock_score(provider_name: str, filename: str, content: bytes) -> float:
    result = await MockDetectorProvider(provider_name).detect(filename, content)
    return result.raw_score * 100.0


def _upsert_analysis(db, claim_id: int, sub: SubScore) -> None:
    row = (db.query(ClaimMediaAnalysis)
           .filter(ClaimMediaAnalysis.claim_id == claim_id,
                   ClaimMediaAnalysis.modality == sub.name).first())
    findings_json = json.dumps({
        "status": sub.status,
        "components": sub.components,
        "findings": [{"detail": f.human_readable, "rule_id": f.rule_id,
                      "points": f.points, "timestamp_or_location": None}
                     for f in sub.findings],
    })
    if row:
        row.provider = sub.provider or "mock"
        row.raw_score = sub.value
        row.findings_json = findings_json
    else:
        db.add(ClaimMediaAnalysis(claim_id=claim_id, modality=sub.name,
                                  provider=sub.provider or "mock",
                                  raw_score=sub.value, findings_json=findings_json))


async def _seed_audio(claim: Claim) -> SubScore:
    filename = claim.audio_url.split("/")[-1]
    path = _media_path(claim.claim_number, claim.audio_url)
    content = path.read_bytes() if path else filename.encode()
    score = await _mock_score("mock_audio", filename, content)
    return SubScore(name="audio", value=score, status="ok", provider="mock_audio")


async def _seed_text(claim: Claim, cfg) -> SubScore:
    # demo seeding ignores the min_chars gate so every claim carries a text score
    corpus = (claim.accident_description or claim.claim_number).strip()
    g = await _mock_score("mock_text_primary", "statement.txt", corpus.encode())
    p = await _mock_score("mock_text_secondary", "statement.txt", corpus.encode())
    value, t_findings = combine_text_scores(g, p, cfg.text.disagreement_gap)
    return SubScore(name="text", value=value, status="ok",
                    provider="mock_text_primary+mock_text_secondary", findings=t_findings)


async def _patch_scored_claim(db, cfg, claim: Claim, latest: ClaimScore) -> None:
    breakdown = ScoreBreakdown.model_validate_json(latest.breakdown_json)
    subs = {s.name: s for s in breakdown.subscores}
    changed = False

    if subs.get("audio") and subs["audio"].status != "ok" and claim.audio_url:
        subs["audio"] = await _seed_audio(claim)
        changed = True
    if subs.get("text") and subs["text"].status != "ok":
        subs["text"] = await _seed_text(claim, cfg)
        changed = True

    if not changed:
        print(f"{claim.claim_number}: audio/text already scored — skipped")
        return
    await _finalize(db, cfg, claim, list(subs.values()), breakdown.payout_cap)


async def _build_legacy_breakdown(db, cfg, claim: Claim) -> None:
    """Legacy claim: derive the 6 signals from old detection rows + seeded fill."""
    analyses = {a.modality: a for a in db.query(ClaimMediaAnalysis)
                .filter(ClaimMediaAnalysis.claim_id == claim.id).all()}
    old_score = claim.fraud_confidence_score or 0.0
    subs: list[SubScore] = []

    # Level 1 metadata + Level 3 consistency: deterministic values tracking the
    # claim's recorded fraud score so the breakdown is coherent with its outcome.
    subs.append(SubScore(
        name="metadata",
        value=_clamp(old_score * 0.6 + _seeded_jitter(claim.claim_number + "meta", -8, 14)),
        status="ok", provider="in_house_metadata_v1"))

    for name, url in (("image", claim.image_url), ("video", claim.video_url)):
        a = analyses.get(name)
        if a and a.raw_score is not None:
            subs.append(SubScore(name=name, value=_clamp(a.raw_score), status="ok",
                                 provider=a.provider))
        elif url:
            subs.append(SubScore(
                name=name,
                value=_clamp(old_score * 0.9 + _seeded_jitter(claim.claim_number + name, -6, 8)),
                status="ok", provider="in_house_pixel_v1"))
        else:
            subs.append(SubScore(name=name, status="not_applicable"))

    a = analyses.get("audio")
    if a and a.raw_score is not None:
        subs.append(SubScore(name="audio", value=_clamp(a.raw_score), status="ok",
                             provider=a.provider))
    elif claim.audio_url:
        subs.append(await _seed_audio(claim))
    else:
        subs.append(SubScore(name="audio", status="not_applicable"))

    a = analyses.get("text")
    if a and a.raw_score is not None:
        subs.append(SubScore(name="text", value=_clamp(a.raw_score), status="ok",
                             provider=a.provider))
    else:
        subs.append(await _seed_text(claim, cfg))

    subs.append(SubScore(
        name="consistency",
        value=_clamp(old_score * 0.7 + _seeded_jitter(claim.claim_number + "cons", -10, 10)),
        status="ok", provider="in_house_consistency_v1"))

    await _finalize(db, cfg, claim, subs, None)


async def _finalize(db, cfg, claim: Claim, subs: list[SubScore], payout_cap) -> None:
    result = fuse(subs, cfg)
    new_breakdown = ScoreBreakdown(
        claim_id=str(claim.claim_number),
        version=next_version(db, str(claim.claim_number)),
        config_version=cfg.config_version,
        subscores=subs,
        weights_used=result["weights_used"],
        base_score=round(result["base_score"], 2),
        final_score=round(result["final_score"], 2),
        escalated=result["escalated"],
        escalation_source=result["escalation_source"],
        routing_band=result["routing_band"],
        forced_review_reason=result["forced_review_reason"],
        payout_cap=payout_cap,
    )
    save_breakdown(db, new_breakdown)

    report = build_artifact_report(new_breakdown)
    try:
        from app.agents.report_synthesizer import synthesize_report
        report = await synthesize_report(report)
    except Exception:
        pass

    claim.fraud_confidence_score = new_breakdown.final_score
    consistency = next((s for s in subs if s.name == "consistency"), None)
    if consistency and consistency.value is not None:
        claim.consistency_score = consistency.value
    claim.artifact_report = json.dumps(report)
    for sub in subs:
        _upsert_analysis(db, claim.id, sub)
    db.commit()
    print(f"{claim.claim_number}: v{new_breakdown.version} "
          f"final={new_breakdown.final_score} band={new_breakdown.routing_band} "
          f"(status kept: {claim.status})")


async def main() -> None:
    cfg = get_config()
    db = SessionLocal()
    for claim in db.query(Claim).order_by(Claim.id).all():
        latest = (db.query(ClaimScore)
                  .filter(ClaimScore.claim_id == str(claim.claim_number))
                  .order_by(ClaimScore.version.desc()).first())
        try:
            if latest:
                await _patch_scored_claim(db, cfg, claim, latest)
            else:
                await _build_legacy_breakdown(db, cfg, claim)
        except Exception as e:
            db.rollback()
            print(f"{claim.claim_number}: FAILED — {type(e).__name__}: {e}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
