"""§10 testing requirements for the Fraud Fusion Scoring engine — fusion, routing,
escalation, re-normalization, fail-safe, append-only, and invariants.
"""
import json

import pytest

from app.scoring.config import get_config
from app.scoring.fusion import fuse
from app.scoring.models import Finding, RoutingBand, ScoreBreakdown, SubScore


CFG = get_config()


def _subs(metadata=None, image=None, video=None, audio=None, text=None, consistency=None,
          statuses=None):
    statuses = statuses or {}
    out = []
    for name, value in [("metadata", metadata), ("image", image), ("video", video),
                        ("audio", audio), ("text", text), ("consistency", consistency)]:
        status = statuses.get(name, "ok" if value is not None else "not_applicable")
        out.append(SubScore(name=name, value=value if status == "ok" else None, status=status))
    return out


# ── §10.2 Worked Example A: clean claim ──────────────────────────────────────
def test_worked_example_a_clean_claim():
    subs = _subs(metadata=6, image=4, video=5, audio=3, text=4, consistency=7)
    r = fuse(subs, CFG)
    assert round(r["base_score"], 2) == 4.84
    assert round(r["final_score"]) == 5
    assert r["routing_band"] == "AUTO_APPROVE"
    assert r["escalated"] is False


# ── §10.3 Worked Example B: AI-generated photos ──────────────────────────────
def test_worked_example_b_ai_photos():
    subs = _subs(metadata=85, image=96, video=20, audio=30, text=55, consistency=88)
    r = fuse(subs, CFG)
    assert round(r["base_score"], 2) == 61.42
    assert r["escalated"] is True
    assert r["escalation_source"] == "image"
    assert r["final_score"] == 91
    assert r["routing_band"] == "SIU_INVESTIGATION"


# ── §10.4 Worked Example C: edited-but-plausible ─────────────────────────────
def test_worked_example_c_edited_plausible():
    subs = _subs(metadata=45, image=60, video=15, audio=12, text=20, consistency=25)
    r = fuse(subs, CFG)
    assert round(r["base_score"], 2) == 29.76
    assert round(r["final_score"]) == 30
    assert r["routing_band"] == "HUMAN_REVIEW"
    assert r["escalated"] is False


# ── §10.5 Re-normalization with video not_applicable ─────────────────────────
def test_renormalization_video_not_applicable():
    subs = _subs(metadata=6, image=4, audio=3, text=4, consistency=7,
                 statuses={"video": "not_applicable"})
    r = fuse(subs, CFG)
    assert abs(sum(r["weights_used"].values()) - 1.0) < 1e-9
    assert "video" not in r["weights_used"]
    # recompute expected: weights /(1-0.22)
    expected = (0.10 * 6 + 0.22 * 4 + 0.18 * 3 + 0.08 * 4 + 0.20 * 7) / 0.78
    assert abs(r["base_score"] - expected) < 1e-9


# ── §10.6 Fail-safe: unavailable audio; failed image forces review ───────────
def test_failsafe_audio_unavailable():
    subs = _subs(metadata=6, image=4, video=5, text=4, consistency=7,
                 statuses={"audio": "unavailable"})
    r = fuse(subs, CFG)
    assert "audio" not in r["weights_used"]
    assert r["routing_band"] in ("AUTO_APPROVE", "HUMAN_REVIEW", "SIU_INVESTIGATION")
    assert r["forced_review_reason"] is None  # only 1 unavailable, no forced flag


def test_failsafe_image_failure_forces_review():
    subs = _subs(metadata=2, video=2, audio=2, text=2, consistency=2,
                 statuses={"image": "unavailable"})
    r = fuse(subs, CFG, forced_review_reasons=["image analysis failed on present media"])
    assert r["forced_review_reason"]
    assert r["routing_band"] == "HUMAN_REVIEW"  # upgraded from AUTO_APPROVE


def test_three_unavailable_forces_review():
    subs = _subs(metadata=2, image=3, video=4,
                 statuses={"audio": "unavailable", "text": "unavailable",
                           "consistency": "unavailable"})
    r = fuse(subs, CFG)
    assert r["forced_review_reason"] is not None
    assert r["routing_band"] == "HUMAN_REVIEW"


def test_forced_review_never_downgrades():
    subs = _subs(metadata=95, image=96, video=95, audio=95, text=95, consistency=95)
    r = fuse(subs, CFG, forced_review_reasons=["whatever"])
    assert r["routing_band"] == "SIU_INVESTIGATION"  # not downgraded to HUMAN_REVIEW


# ── §10.7 Escalation edge cases ──────────────────────────────────────────────
def test_escalation_at_exactly_90():
    subs = _subs(metadata=10, image=90, video=10, audio=10, text=10, consistency=10)
    r = fuse(subs, CFG)
    assert r["escalated"] is True
    assert r["final_score"] == 85  # max(base, 90-5)


def test_no_escalation_at_89_99():
    subs = _subs(metadata=10, image=89.99, video=10, audio=10, text=10, consistency=10)
    r = fuse(subs, CFG)
    assert r["escalated"] is False


def test_final_clamped_to_100():
    subs = _subs(metadata=100, image=100, video=100, audio=100, text=100, consistency=100)
    r = fuse(subs, CFG)
    assert r["final_score"] <= 100


# ── Only AI-manipulation signals trigger worst-signal escalation ─────────────
def test_metadata_alone_cannot_escalate():
    subs = _subs(metadata=100, image=10, video=10, audio=10, text=10, consistency=10)
    r = fuse(subs, CFG)
    assert r["escalated"] is False
    assert r["final_score"] == r["base_score"]


def test_consistency_alone_cannot_escalate_without_ch3():
    subs = _subs(metadata=10, image=10, video=10, audio=10, text=10, consistency=95)
    r = fuse(subs, CFG)
    assert r["escalated"] is False


def test_each_ai_manipulation_signal_can_escalate():
    for signal in ("image", "video", "audio", "text"):
        kwargs = dict(metadata=10, image=10, video=10, audio=10, text=10, consistency=10)
        kwargs[signal] = 95
        r = fuse(_subs(**kwargs), CFG)
        assert r["escalated"] is True and r["escalation_source"] == signal


# ── §10.8 External-match (C-H3) escalation via virtual signal ────────────────
def test_external_match_virtual_signal_escalation():
    subs = _subs(metadata=6, image=4, video=5, audio=3, text=4, consistency=60)
    subs[5].findings.append(Finding(
        rule_id="C-H3", severity="high", points=50, escalation_eligible=True,
        human_readable="Photo found on the public web.",
    ))
    r = fuse(subs, CFG)
    assert r["escalated"] is True
    assert r["escalation_source"] == "consistency"
    assert r["final_score"] == max(r["base_score"], 87)
    assert r["routing_band"] == "SIU_INVESTIGATION"


# ── §10.11 WhatsApp nuance: stripped EXIF alone can't leave AUTO_APPROVE ─────
def test_whatsapp_stripped_exif_weak_signal():
    metadata_only = CFG.metadata.low  # M-L1 only → S_metadata = 8
    assert metadata_only == 8
    subs = _subs(metadata=metadata_only, image=0, video=0, audio=0, text=0, consistency=0)
    r = fuse(subs, CFG)
    assert CFG.fusion.weights["metadata"] * metadata_only < CFG.fusion.routing.auto_approve_below
    assert r["routing_band"] == "AUTO_APPROVE"


# ── §10.1 Determinism: same inputs → byte-identical breakdown ────────────────
def test_determinism_five_runs():
    payloads = []
    for _ in range(5):
        subs = _subs(metadata=45, image=60, video=15, audio=12, text=20, consistency=25)
        r = fuse(subs, CFG)
        bd = ScoreBreakdown(
            claim_id="CLM-TEST-1", version=1, config_version=CFG.config_version,
            subscores=subs, weights_used=r["weights_used"],
            base_score=r["base_score"], final_score=r["final_score"],
            escalated=r["escalated"], escalation_source=r["escalation_source"],
            routing_band=r["routing_band"], forced_review_reason=r["forced_review_reason"],
        )
        d = json.loads(bd.model_dump_json())
        d.pop("created_at")
        payloads.append(json.dumps(d, sort_keys=True))
    assert len(set(payloads)) == 1


# ── §10.10 No-denial invariant ───────────────────────────────────────────────
def test_no_denial_routing_values():
    import typing
    bands = set(typing.get_args(RoutingBand))
    assert bands == {"AUTO_APPROVE", "HUMAN_REVIEW", "SIU_INVESTIGATION"}
    # grep-level: the fusion module exposes no deny/reject routing value
    import inspect
    import app.scoring.fusion as fusion_mod
    src = inspect.getsource(fusion_mod).lower()
    assert "deny" not in src and "reject" not in src
