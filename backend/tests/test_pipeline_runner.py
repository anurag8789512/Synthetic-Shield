"""A claim must never stay in "processing": crashes route to review, restarts resume."""
import asyncio

from app.agents import orchestrator, pipeline_runner
from app.models import AuditTrail, ClaimAssignment


def test_pipeline_crash_routes_claim_to_moderator_review(db, test_claim, test_officer, monkeypatch):
    test_claim.status = "processing"
    db.commit()

    async def _boom(claim_id, session):
        raise RuntimeError("scoring exploded")
    monkeypatch.setattr(orchestrator, "process_claim", _boom)

    asyncio.run(pipeline_runner._run(test_claim.id, test_claim.claim_number, None))

    db.expire_all()
    assert test_claim.status == "moderator_review"
    actions = [a.action for a in db.query(AuditTrail).filter_by(claim_id=test_claim.id)]
    assert "analysis_failed" in actions
    assert db.query(ClaimAssignment).filter_by(claim_id=test_claim.id, officer_id=test_officer.id).count() == 1


def test_crash_after_routing_keeps_the_pipeline_decision(db, test_claim, monkeypatch):
    test_claim.status = "processing"
    db.commit()

    async def _routed_then_boom(claim_id, session):
        c = session.get(type(test_claim), claim_id)
        c.status = "siu_investigation"
        session.commit()
        raise RuntimeError("notification failed")
    monkeypatch.setattr(orchestrator, "process_claim", _routed_then_boom)

    asyncio.run(pipeline_runner._run(test_claim.id, test_claim.claim_number, None))
    db.expire_all()
    assert test_claim.status == "siu_investigation"


def test_resume_restarts_only_processing_claims(db, test_claim, monkeypatch):
    test_claim.status = "processing"
    test_claim.video_url = "http://localhost:8000/media/CLM-2026-TEST01/dashcam.mp4"
    db.commit()
    started = []
    monkeypatch.setattr(pipeline_runner, "start_pipeline", lambda *a: started.append(a))

    assert pipeline_runner.resume_interrupted_claims() == [test_claim.claim_number]
    assert started == [(test_claim.id, test_claim.claim_number, "dashcam.mp4")]

    test_claim.status = "auto_approved"
    db.commit()
    started.clear()
    assert pipeline_runner.resume_interrupted_claims() == []
    assert started == []
