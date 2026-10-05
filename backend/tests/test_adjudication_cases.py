"""End-to-end adjudication test cases: a genuine claim (auto-approve + payout)
and a suspicious-but-inconclusive claim (moderator review + assignment).

The fusion engine itself is pinned by tests/scoring/; here we feed its two
canonical worked examples through the REAL pipeline (adapter → status →
payout/assignment → queue routing → audit trail).
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.orchestrator import process_claim
from app.models import AuditTrail, ClaimAssignment, Payout
from app.scoring.config import get_config
from app.scoring.models import ScoreBreakdown, SubScore


def _breakdown(values: dict, base: float, final: float, band: str, claim_number: str) -> ScoreBreakdown:
    cfg = get_config()
    subs = [SubScore(name=n, value=v, status="ok") for n, v in values.items()]
    return ScoreBreakdown(
        claim_id=claim_number, version=1, config_version=cfg.config_version,
        subscores=subs, weights_used=cfg.fusion.weights,
        base_score=base, final_score=final, escalated=False,
        routing_band=band,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Test case 1: GENUINE CLAIM → auto-approved, paid out, review-only in queue ─

@pytest.mark.asyncio
async def test_genuine_claim_auto_approved_end_to_end(client, db, test_claim, officer_token):
    test_claim.status = "processing"
    db.commit()

    # worked example A: clean claim → Base 4.84 → AUTO_APPROVE
    breakdown = _breakdown(
        {"metadata": 6, "image": 4, "video": 5, "audio": 3, "text": 4, "consistency": 7},
        base=4.84, final=4.84, band="AUTO_APPROVE", claim_number=test_claim.claim_number,
    )

    with patch("app.agents.scoring_adapter.run_scoring", new_callable=AsyncMock, return_value=breakdown), \
         patch("app.agents.report_synthesizer.synthesize_report", new_callable=AsyncMock, side_effect=lambda r: r), \
         patch("app.agents.orchestrator.evaluate_claim_valuation", new_callable=AsyncMock,
               return_value={"method": "test", "approved_amount_cents": 123400}), \
         patch("app.agents.orchestrator.notify_claim_status", new_callable=AsyncMock) as notify:
        await process_claim(test_claim.id, db)

    db.refresh(test_claim)
    assert test_claim.status == "auto_approved"
    assert test_claim.fraud_confidence_score == 4.84

    # payout initiated with the valuation-approved amount
    payout = db.query(Payout).filter(Payout.claim_id == test_claim.id).first()
    assert payout is not None and payout.status == "initiated"
    assert test_claim.payout_amount_cents == 123400
    assert test_claim.payout_transaction_id

    # customer notified with the auto-approval template
    assert notify.await_args.args[2] == "auto_approved"

    # artifact report carries the full score division
    report = json.loads(test_claim.artifact_report)
    assert report["score_breakdown"]["final_score"] == 4.84
    assert report["score_breakdown"]["routing_band"] == "AUTO_APPROVE"

    # queue routing: pinned review-only, attributed to the system
    row = next(c for c in client.get("/claims/queue/all", headers=_auth(officer_token)).json()
               if c["id"] == test_claim.id)
    assert row["in_queue"] is True
    assert row["queue_action"] == "review_only"
    assert row["decided_by"] == "system"
    assert row["in_case_files"] is True

    # audit trail recorded scoring + payout
    actions = {t.action for t in db.query(AuditTrail).filter(AuditTrail.claim_id == test_claim.id)}
    assert {"claim_received", "fusion_scores_recorded", "adjudication_routed", "payout_initiated"} <= actions


# ── Test case 2: SUSPICIOUS CLAIM → moderator review, assigned, no payout ──────

@pytest.mark.asyncio
async def test_suspicious_claim_routed_to_moderator_end_to_end(client, db, test_claim, test_officer, officer_token):
    test_claim.status = "processing"
    db.commit()

    # worked example C: edited-but-plausible → Base 29.76 → HUMAN_REVIEW
    breakdown = _breakdown(
        {"metadata": 45, "image": 60, "video": 15, "audio": 12, "text": 20, "consistency": 25},
        base=29.76, final=29.76, band="HUMAN_REVIEW", claim_number=test_claim.claim_number,
    )

    with patch("app.agents.scoring_adapter.run_scoring", new_callable=AsyncMock, return_value=breakdown), \
         patch("app.agents.report_synthesizer.synthesize_report", new_callable=AsyncMock, side_effect=lambda r: r), \
         patch("app.agents.orchestrator.notify_claim_status", new_callable=AsyncMock) as notify:
        await process_claim(test_claim.id, db)

    db.refresh(test_claim)
    assert test_claim.status == "moderator_review"
    assert test_claim.fraud_confidence_score == 29.76

    # a moderator was assigned, workload-tracked
    assignment = db.query(ClaimAssignment).filter(
        ClaimAssignment.claim_id == test_claim.id,
        ClaimAssignment.assignment_type == "moderator_review",
    ).first()
    assert assignment is not None and assignment.status == "pending"
    assert assignment.officer_id == test_officer.id

    # NO payout for a claim pending human review
    assert db.query(Payout).filter(Payout.claim_id == test_claim.id).first() is None
    assert notify.await_args.args[2] == "moderator_review"

    # queue routing: actionable moderate entry, not decided by anyone yet
    row = next(c for c in client.get("/claims/queue/all", headers=_auth(officer_token)).json()
               if c["id"] == test_claim.id)
    assert row["in_queue"] is True
    assert row["queue_action"] == "moderate"
    assert row["decided_by"] is None
    assert row["in_case_files"] is False

    # moderator can then approve it (closing the loop)
    resp = client.post(f"/claims/{test_claim.id}/moderator-approve", headers=_auth(officer_token))
    assert resp.status_code == 200
    db.refresh(test_claim)
    assert test_claim.status == "auto_approved"
    assert db.query(Payout).filter(Payout.claim_id == test_claim.id).first() is not None
