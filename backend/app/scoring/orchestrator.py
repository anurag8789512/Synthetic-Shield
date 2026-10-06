"""Scoring orchestrator: run_scoring(claim_id) coordinates all analyzers,
runs fusion, and persists an append-only ScoreBreakdown (spec §1, §6).

Deterministic; no LLM anywhere in this path. Analyzer failures mark their
sub-score unavailable and never crash the pipeline (§0.7).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim, ClaimDocument, Coverage, Policy
from app.scoring import persistence
from app.scoring.config import ScoringConfig, get_config
from app.scoring.fusion import fuse
from app.scoring.level1_metadata.analyzer import (
    MetadataAnalyzer, compute_phash, extract_container_meta,
    extract_image_meta, parse_latlon, _sha256,
)
from app.scoring.level2_manipulation.image_pixel import ImagePixelAnalyzer
from app.scoring.level2_manipulation.video_pixel import VideoPixelAnalyzer
from app.scoring.level2_manipulation.providers.base import (
    DetectorProvider, MockDetectorProvider, ProviderError, call_with_retries,
)
from app.scoring.level2_manipulation.providers.gptzero_text import GPTZeroTextProvider
from app.scoring.level2_manipulation.providers.pangram_text import PangramTextProvider
from app.scoring.level2_manipulation.providers.resemble_audio import ResembleAudioProvider
from app.scoring.level3_consistency.engine import ConsistencyEngine
from app.scoring.level3_consistency.part_pricing import (
    MockPartPricingProvider, get_part_pricing_provider,
)
from app.scoring.level3_consistency.reverse_search import (
    MockReverseSearchProvider, get_reverse_search_provider,
)
from app.scoring.level3_consistency.weather import MockWeatherProvider, get_weather_provider
from app.scoring.models import Finding, ScoreBreakdown, SubScore
from app.scoring.stt import transcribe

MEDIA_ROOT = Path("app/media_store")


def _demo() -> bool:
    return bool(settings.SCORING_DEMO_MODE)


def get_audio_provider(cfg: ScoringConfig) -> DetectorProvider | None:
    """None when the configured detector cannot run (missing key / unknown name);
    the audio sub-score is then marked unavailable. Mocks only run in demo mode
    or when explicitly configured — never as a silent production fallback."""
    name = "mock" if _demo() else settings.AUDIO_DETECTOR_PROVIDER
    if name == "resemble":
        if not settings.RESEMBLE_AI_API_KEY:
            print("[SCORING] RESEMBLE_AI_API_KEY missing — audio sub-score unavailable")
            return None
        return ResembleAudioProvider(timeout_s=cfg.providers.timeout_s)
    if name == "mock":
        return MockDetectorProvider("mock_audio")
    print(f"[SCORING] unknown AUDIO_DETECTOR_PROVIDER '{name}' — audio sub-score unavailable")
    return None


def get_text_providers(cfg: ScoringConfig) -> tuple[DetectorProvider | None, DetectorProvider | None]:
    if _demo():
        return MockDetectorProvider("mock_text_primary"), MockDetectorProvider("mock_text_secondary")
    providers: list[DetectorProvider | None] = []
    for role, name in (("primary", settings.TEXT_DETECTOR_PRIMARY),
                       ("secondary", settings.TEXT_DETECTOR_SECONDARY)):
        if name == "gptzero":
            providers.append(GPTZeroTextProvider(timeout_s=cfg.providers.timeout_s)
                             if settings.GPTZERO_API_KEY else None)
        elif name == "pangram":
            providers.append(PangramTextProvider(timeout_s=cfg.providers.timeout_s)
                             if settings.PANGRAM_API_KEY else None)
        elif name == "mock":
            providers.append(MockDetectorProvider(f"mock_text_{role}"))
        else:
            providers.append(None)
        if providers[-1] is None and name != "none":
            print(f"[SCORING] text detector '{name}' ({role}) not configured — skipped")
    return providers[0], providers[1]


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    """Whole-word match where only letters count as word chars, so "fraud_test"
    hits but "realistic" doesn't."""
    return any(re.search(rf"(?<![a-z]){w}(?![a-z])", text) for w in words)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _media_path(claim_number: str, url: str | None) -> Path | None:
    if not url:
        return None
    p = MEDIA_ROOT / claim_number / url.split("/")[-1]
    return p if p.exists() else None


async def _detect_or_none(provider: DetectorProvider, filename: str, content: bytes,
                          cfg: ScoringConfig) -> tuple[float | None, str]:
    """Run a foreign detector with retries. On failure returns (None, name) so the
    sub-score is marked unavailable (weights re-normalize, forced-review rules
    apply) — never a substituted mock score.
    Returns (score, provider_name_actually_used)."""
    try:
        result = await call_with_retries(
            lambda: provider.detect(filename, content),
            retries=cfg.providers.retries, timeout_s=cfg.providers.timeout_s,
            provider_name=provider.provider_name,
        )
    except ProviderError:
        print(f"[SCORING] {provider.provider_name} failed — sub-score unavailable")
        return None, provider.provider_name
    raw = result.raw_score
    if not provider.SCORE_IS_FAKE_PROBABILITY:
        raw = 1.0 - raw
    return max(0.0, min(1.0, raw)) * 100.0, provider.provider_name


def combine_text_scores(g: float | None, p: float | None, disagreement_gap: float) -> tuple[float | None, list[Finding]]:
    """§4.4 cross-check rule: agreement gate → conservative min; disagreement → average."""
    findings: list[Finding] = []
    if g is not None and p is not None:
        if abs(g - p) <= disagreement_gap:
            return min(g, p), findings
        findings.append(Finding(
            rule_id="T-DISAGREE", severity="info", points=0.0,
            human_readable=(f"Text detectors disagree strongly (primary {g:.0f}/100 vs "
                            f"secondary {p:.0f}/100); using their average."),
            extra={"primary": g, "secondary": p},
        ))
        return (g + p) / 2.0, findings
    single = g if g is not None else p
    if single is not None:
        findings.append(Finding(
            rule_id="T-SINGLE", severity="info", points=0.0,
            human_readable="Only one text detector was available; single-detector mode.",
        ))
        return single, findings
    return None, findings


async def run_scoring(claim_id: int, db: DBSession) -> ScoreBreakdown:
    config = get_config()
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise ValueError(f"claim {claim_id} not found")

    coverage = db.query(Coverage).filter(Coverage.id == claim.coverage_id).first()
    policy = db.query(Policy).filter(Policy.id == claim.policy_id).first() if claim.policy_id else None
    policy_start = _parse_date(policy.issued_date) if policy else None
    documents = db.query(ClaimDocument).filter(ClaimDocument.claim_id == claim_id).all()

    video_path = _media_path(claim.claim_number, claim.video_url)
    image_path = _media_path(claim.claim_number, claim.image_url)
    audio_path = _media_path(claim.claim_number, claim.audio_url)
    doc_paths = [p for d in documents if (p := _media_path(claim.claim_number, d.file_url))]

    # Speech-to-text for fact extraction (never used for scoring judgments).
    # CPU-heavy sync work runs on worker threads (asyncio.to_thread) so the
    # event loop keeps serving API requests while a claim is being analyzed.
    if audio_path and not claim.transcript_text and not _demo():
        transcript = await asyncio.to_thread(transcribe, audio_path)
        if transcript:
            claim.transcript_text = transcript
            db.commit()

    forced_reasons: list[str] = []
    subscores: list[SubScore] = []

    # ---- Level 1: metadata ----
    try:
        files = []
        if image_path:
            files.append({"path": image_path, "media_type": "image",
                          "captured_in_app": False, "claimed_official": False})
        if video_path:
            # the mobile app uploads video via the file picker — not an in-app capture
            files.append({"path": video_path, "media_type": "video",
                          "captured_in_app": False, "claimed_official": False})
        if audio_path:
            files.append({"path": audio_path, "media_type": "audio",
                          "captured_in_app": False, "claimed_official": False})
        for p in doc_paths:
            files.append({"path": p, "media_type": "pdf",
                          "captured_in_app": False, "claimed_official": True})
        s_metadata = MetadataAnalyzer(config).analyze(
            db, str(claim.claim_number), files,
            claimed_location=claim.accident_location,
            submission_dt=claim.created_at, policy_start=policy_start,
        )
    except Exception as e:
        print(f"[SCORING] metadata analyzer failed: {type(e).__name__}: {e}")
        s_metadata = SubScore(name="metadata", status="unavailable", provider="in_house_metadata_v1")
    subscores.append(s_metadata)

    # ---- Level 2: image (in-house pixel) ----
    if image_path:
        try:
            image_meta = extract_image_meta(image_path)
            camera_original = bool(image_meta.get("make") or image_meta.get("model"))
            s_image = await asyncio.to_thread(ImagePixelAnalyzer(config).analyze, image_path,
                                              camera_original)
        except Exception as e:
            print(f"[SCORING] image pixel analyzer failed: {type(e).__name__}: {e}")
            s_image = SubScore(name="image", status="unavailable", provider="in_house_pixel_v1")
            forced_reasons.append("image analysis failed on present media")
    else:
        s_image = SubScore(name="image", status="not_applicable", provider="in_house_pixel_v1")
    subscores.append(s_image)

    # ---- Level 2: video (in-house frame-level) ----
    if video_path:
        try:
            s_video = await asyncio.to_thread(VideoPixelAnalyzer(config).analyze, video_path)
            if s_video.status == "unavailable":
                forced_reasons.append("video analysis failed on present media")
            else:
                # index keyframe hashes for future internal reverse search
                await asyncio.to_thread(_index_video_keyframes, db, claim, video_path)
        except Exception as e:
            print(f"[SCORING] video pixel analyzer failed: {type(e).__name__}: {e}")
            s_video = SubScore(name="video", status="unavailable", provider="in_house_pixel_v1")
            forced_reasons.append("video analysis failed on present media")
    else:
        s_video = SubScore(name="video", status="not_applicable", provider="in_house_pixel_v1")
    subscores.append(s_video)

    # ---- Level 2: audio (foreign detector) ----
    if audio_path:
        provider = get_audio_provider(config)
        score = None
        provider_used = (provider.provider_name if provider
                         else f"{settings.AUDIO_DETECTOR_PROVIDER} (not configured)")
        if provider:
            try:
                score, provider_used = await _detect_or_none(provider, audio_path.name,
                                                             audio_path.read_bytes(), config)
            except Exception as e:
                print(f"[SCORING] audio detection failed: {type(e).__name__}: {e}")
        if score is None:
            s_audio = SubScore(name="audio", status="unavailable", provider=provider_used)
        else:
            s_audio = SubScore(name="audio", value=score, status="ok", provider=provider_used)
    else:
        s_audio = SubScore(name="audio", status="not_applicable")
    subscores.append(s_audio)

    # ---- Level 2: text (foreign detectors, cross-checked) ----
    text_corpus = (claim.accident_description or "").strip()
    if len(text_corpus) >= config.text.min_chars:
        primary, secondary = get_text_providers(config)
        g, g_prov = await _detect_or_none(primary, "statement.txt", text_corpus.encode(), config) if primary else (None, None)
        p, p_prov = await _detect_or_none(secondary, "statement.txt", text_corpus.encode(), config) if secondary else (None, None)
        value, t_findings = combine_text_scores(g, p, config.text.disagreement_gap)
        if value is None:
            s_text = SubScore(name="text", status="unavailable",
                              provider=g_prov or p_prov or "text detectors (not configured)")
        else:
            s_text = SubScore(name="text", value=value, status="ok",
                              provider="+".join(n for n in (g_prov, p_prov) if n),
                              findings=t_findings)
    else:
        s_text = SubScore(name="text", status="not_applicable")
    subscores.append(s_text)

    # ---- Level 3: consistency ----
    # §5.3 gate for external reverse search on the provisional signals
    provisional = fuse([s for s in subscores], config)
    suspicious = (provisional["base_score"] >= 15
                  or any(s.value is not None and s.value >= 50 for s in subscores))
    run_external = (config.consistency.external_reverse_search == "always"
                    or (config.consistency.external_reverse_search == "suspicious_only" and suspicious))

    media_dtos: list[str] = []
    if image_path:
        dto = extract_image_meta(image_path).get("datetime_original")
        if dto:
            media_dtos.append(dto)
    if video_path:
        dto = extract_container_meta(video_path).get("datetime_original")
        if dto:
            media_dtos.append(dto)

    public_image_urls = []
    if claim.image_url and claim.image_url.startswith("http") and "localhost" not in claim.image_url:
        public_image_urls.append(claim.image_url)

    try:
        weather = MockWeatherProvider() if _demo() else get_weather_provider()
        reverse = MockReverseSearchProvider() if _demo() else get_reverse_search_provider()
        pricing = MockPartPricingProvider() if _demo() else get_part_pricing_provider()
        engine = ConsistencyEngine(config, weather, reverse, pricing)
        s_consistency = await engine.analyze(
            transcript=claim.transcript_text,
            written_description=claim.accident_description,
            photo_zone=None,  # no in-house damage-region classifier yet
            incident_dt=claim.incident_at,  # optional, claimant's local time
            location=parse_latlon(claim.accident_location),
            media_datetime_originals=media_dtos,
            claim_amount=(claim.claim_amount_cents / 100.0) if claim.claim_amount_cents else None,
            vehicle_description="car",
            region=claim.accident_location or "",
            coverage_limit=(coverage.coverage_limit_cents / 100.0)
                           if coverage and coverage.coverage_limit_cents else None,
            image_urls_for_external_search=public_image_urls,
            run_external_search=run_external,
        )
    except Exception as e:
        print(f"[SCORING] consistency engine failed: {type(e).__name__}: {e}")
        s_consistency = SubScore(name="consistency", status="unavailable",
                                 provider="in_house_consistency_v1")
    subscores.append(s_consistency)

    payout_cap = s_consistency.components.pop("payout_cap", -1.0) if s_consistency.components else -1.0
    payout_cap = None if payout_cap is None or payout_cap < 0 else payout_cap

    # Demo-mode only: media filename triggers force deterministic routing so
    # recorded demos reliably land in moderator review / auto-approve.
    if _demo():
        trigger_key = " ".join(p.name.lower() for p in (video_path, image_path) if p)
        profile = None
        if _has_word(trigger_key, ("fraud", "fake", "synthetic")):
            profile = {"metadata": 48.0, "image": 72.0, "video": 78.0,
                       "audio": 64.0, "text": 55.0, "consistency": 60.0}
        elif _has_word(trigger_key, ("clean", "real", "genuine")):
            profile = {"metadata": 6.0, "image": 8.0, "video": 5.0,
                       "audio": 4.0, "text": 3.0, "consistency": 2.0}
        if profile:
            print(f"[SCORING] demo trigger profile applied ({trigger_key})")
            for s in subscores:
                if s.name in profile and s.status != "not_applicable":
                    s.value = profile[s.name]
                    s.status = "ok"
            # every analyzer the reasons refer to was just overridden to "ok"
            forced_reasons = []

    # ---- Fusion ----
    result = fuse(subscores, config, forced_review_reasons=forced_reasons)

    breakdown = ScoreBreakdown(
        claim_id=str(claim.claim_number),
        version=persistence.next_version(db, str(claim.claim_number)),
        config_version=config.config_version,
        subscores=subscores,
        weights_used=result["weights_used"],
        base_score=round(result["base_score"], 2),
        final_score=round(result["final_score"], 2),
        escalated=result["escalated"],
        escalation_source=result["escalation_source"],
        routing_band=result["routing_band"],
        forced_review_reason=result["forced_review_reason"],
        payout_cap=payout_cap,
        created_at=datetime.utcnow(),
    )
    persistence.save_breakdown(db, breakdown)
    return breakdown


def _index_video_keyframes(db: DBSession, claim: Claim, video_path: Path) -> None:
    """Hash sampled keyframes into evidence_hashes for internal reverse search."""
    import tempfile
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(int(round(fps * 5)), 1)  # one keyframe every ~5 seconds
        idx = saved = 0
        while saved < 6:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                cv2.imwrite(str(tmp_path), frame)
                try:
                    persistence.record_evidence_hash(
                        db, str(claim.claim_number), f"{video_path.name}#kf{saved}",
                        _sha256(tmp_path), compute_phash(tmp_path), "video_keyframe",
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)
                saved += 1
            idx += 1
        cap.release()
    except Exception as e:
        print(f"[SCORING] keyframe indexing failed: {type(e).__name__}: {e}")
