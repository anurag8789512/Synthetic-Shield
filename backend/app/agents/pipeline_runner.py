"""Background runner for the claim pipeline.

Guarantees a claim never sits in "processing" forever:
- a pipeline exception routes the claim to moderator review ("analysis_failed");
- on startup, claims left in "processing" by a restart/crash are re-run.

`session_factory` is module-level so tests can point background work at the
test database instead of claims.db.
"""
from __future__ import annotations

import asyncio

from app.database import SessionLocal
from app.models import Claim

session_factory = SessionLocal
_background_tasks: set[asyncio.Task] = set()


def start_pipeline(claim_id: int, claim_number: str, video_filename: str | None = None) -> asyncio.Task:
    """Schedule the full pipeline for a claim (strong ref prevents GC mid-run)."""
    task = asyncio.create_task(_run(claim_id, claim_number, video_filename))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _run(claim_id: int, claim_number: str, video_filename: str | None) -> None:
    from app.agents.orchestrator import process_claim
    from app.providers.storage import ensure_browser_playable_video
    db = session_factory()
    try:
        if video_filename:
            await asyncio.to_thread(ensure_browser_playable_video, claim_number, video_filename)
        await process_claim(claim_id, db)
    except Exception as e:
        print(f"[PIPELINE ERROR] Claim {claim_id}: {type(e).__name__}: {e}")
        _route_failed_claim(claim_id, f"{type(e).__name__}: {e}")
    finally:
        db.close()


def _route_failed_claim(claim_id: int, error: str) -> None:
    """Hand a claim whose automated analysis crashed to a human instead of
    leaving it in "processing". Only acts if the pipeline hadn't routed it yet."""
    from app.agents.assignment_agent import assign_moderator
    from app.agents.audit_logger import log_event
    db = session_factory()
    try:
        claim = db.query(Claim).filter(Claim.id == claim_id).first()
        if not claim or claim.status != "processing":
            return
        claim.status = "moderator_review"
        db.commit()
        log_event(db, claim_id, "system", "analysis_failed",
                  details={"error": error[:500], "routed_to": "moderator_review"})
        try:
            officer_id = assign_moderator(claim_id, db)
            log_event(db, claim_id, "system", "moderator_assigned", details={"officer_id": officer_id})
        except Exception as e:
            print(f"[PIPELINE ERROR] Claim {claim_id}: moderator assignment failed: {e}")
    finally:
        db.close()


def resume_interrupted_claims() -> list[str]:
    """Re-run every claim left in "processing" (e.g. the server restarted while it
    was being analyzed). Call once at startup, inside the running event loop."""
    from app.agents.audit_logger import log_event
    db = session_factory()
    try:
        stuck = db.query(Claim).filter(Claim.status == "processing").order_by(Claim.id).all()
        resumed = []
        for claim in stuck:
            log_event(db, claim.id, "system", "analysis_resumed",
                      details={"reason": "claim was still processing when the server (re)started"})
            video_filename = claim.video_url.rsplit("/", 1)[-1] if claim.video_url else None
            start_pipeline(claim.id, claim.claim_number, video_filename)
            resumed.append(claim.claim_number)
        if resumed:
            print(f"[PIPELINE] resuming interrupted claims: {', '.join(resumed)}")
        return resumed
    finally:
        db.close()
