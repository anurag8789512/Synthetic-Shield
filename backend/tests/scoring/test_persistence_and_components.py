"""§10.9 append-only persistence + §10.12 image component gating + provider
direction constants + text cross-check rule.
"""
import numpy as np
import pytest
from PIL import Image

from app.scoring.config import get_config
from app.scoring.models import Finding, ScoreBreakdown, SubScore
from app.scoring.orchestrator import combine_text_scores
from app.scoring.persistence import AppendOnlyViolation, ClaimScore, save_breakdown

CFG = get_config()


def _breakdown(claim_id="CLM-TEST-9", version=1):
    subs = [SubScore(name="metadata", value=5.0, status="ok",
                     findings=[Finding(rule_id="M-L1", severity="low", points=8,
                                       human_readable="test finding")])]
    return ScoreBreakdown(
        claim_id=claim_id, version=version, config_version=CFG.config_version,
        subscores=subs, weights_used={"metadata": 1.0},
        base_score=5.0, final_score=5.0, escalated=False,
        routing_band="AUTO_APPROVE",
    )


# ── §10.9 Append-only: update/delete raises ──────────────────────────────────
def test_append_only_update_raises(db):
    row = save_breakdown(db, _breakdown())
    row.final_score = 99.0
    with pytest.raises(AppendOnlyViolation):
        db.commit()
    db.rollback()


def test_append_only_delete_raises(db):
    row = save_breakdown(db, _breakdown(version=1))
    db.delete(row)
    with pytest.raises(AppendOnlyViolation):
        db.commit()
    db.rollback()


def test_rescore_creates_new_version(db):
    from app.scoring.persistence import next_version
    save_breakdown(db, _breakdown(version=1))
    assert next_version(db, "CLM-TEST-9") == 2
    save_breakdown(db, _breakdown(version=2))
    rows = db.query(ClaimScore).filter(ClaimScore.claim_id == "CLM-TEST-9").all()
    assert {r.version for r in rows} == {1, 2}


# ── §10.12 Image component gating: PNG skips jpeg_dq, re-normalizes ──────────
def test_png_skips_jpeg_dq(tmp_path):
    from app.scoring.level2_manipulation.image_pixel import ImagePixelAnalyzer
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
    png_path = tmp_path / "photo.png"
    Image.fromarray(arr).save(png_path)

    sub = ImagePixelAnalyzer(CFG).analyze(png_path)
    assert sub.status == "ok"
    assert "jpeg_dq" not in sub.components
    assert set(sub.components) <= {"ela", "noise", "freq"}


def test_jpeg_includes_dq_component(tmp_path):
    from app.scoring.level2_manipulation.image_pixel import ImagePixelAnalyzer
    rng = np.random.default_rng(7)
    arr = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
    jpg_path = tmp_path / "photo.jpg"
    Image.fromarray(arr).save(jpg_path, quality=90)

    sub = ImagePixelAnalyzer(CFG).analyze(jpg_path)
    assert sub.status == "ok"
    assert "jpeg_dq" in sub.components


def test_image_analysis_deterministic(tmp_path):
    from app.scoring.level2_manipulation.image_pixel import ImagePixelAnalyzer
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 255, size=(96, 96, 3), dtype=np.uint8)
    jpg_path = tmp_path / "same.jpg"
    Image.fromarray(arr).save(jpg_path, quality=90)
    values = {ImagePixelAnalyzer(CFG).analyze(jpg_path).value for _ in range(3)}
    assert len(values) == 1


# ── §4.3/§4.4 provider direction constants ───────────────────────────────────
def test_provider_direction_constants():
    from app.scoring.level2_manipulation.providers.gptzero_text import GPTZeroTextProvider
    from app.scoring.level2_manipulation.providers.pangram_text import PangramTextProvider
    from app.scoring.level2_manipulation.providers.resemble_audio import ResembleAudioProvider
    assert ResembleAudioProvider.SCORE_IS_FAKE_PROBABILITY is True
    assert GPTZeroTextProvider.SCORE_IS_FAKE_PROBABILITY is True
    assert PangramTextProvider.SCORE_IS_FAKE_PROBABILITY is True


# ── §4.4 text cross-check combination rule ───────────────────────────────────
def test_text_agreement_uses_conservative_min():
    value, findings = combine_text_scores(40.0, 55.0, CFG.text.disagreement_gap)
    assert value == 40.0
    assert not findings


def test_text_disagreement_averages_with_finding():
    value, findings = combine_text_scores(20.0, 80.0, CFG.text.disagreement_gap)
    assert value == 50.0
    assert any(f.rule_id == "T-DISAGREE" for f in findings)


def test_text_single_detector_mode():
    value, findings = combine_text_scores(None, 66.0, CFG.text.disagreement_gap)
    assert value == 66.0
    assert any(f.rule_id == "T-SINGLE" for f in findings)


def test_text_none_available():
    value, findings = combine_text_scores(None, None, CFG.text.disagreement_gap)
    assert value is None
