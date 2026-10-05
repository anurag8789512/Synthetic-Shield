"""
Moderator endpoints: approve or reject claims in moderator_review status.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Claim, User, ModeratorAction, Payout, ClaimAssignment, ClaimsOfficer
from app.config import settings
from app.auth_deps import get_current_officer
from app.agents.notification_agent import notify_claim_status
from app.agents.audit_logger import log_event

router = APIRouter(prefix="/claims", tags=["moderator"])


class RejectBody(BaseModel):
    reason: str


@router.post("/{claim_id}/review-done")
async def review_done(
    claim_id: int,
    current_officer: ClaimsOfficer = Depends(get_current_officer),
    db: DBSession = Depends(get_db),
):
    """Officer acknowledges a system-auto-approved claim; it leaves the Queue
    and lives on in Case Files only. The payout already happened — this is a
    review acknowledgement, not an approval decision."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if claim.status != "auto_approved":
        raise HTTPException(status_code=400, detail=f"Claim is not auto-approved (current: {claim.status}).")

    existing = db.query(ModeratorAction).filter(ModeratorAction.claim_id == claim_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Claim review is already recorded.")

    db.add(ModeratorAction(
        claim_id=claim.id,
        officer_id=current_officer.id,
        decision="review_done",
    ))
    db.commit()

    log_event(db, claim_id, "officer", "review_completed", actor_id=current_officer.name,
              details={"note": "auto-approved claim reviewed and acknowledged"})

    return {"status": "review_done", "claim_number": claim.claim_number}


@router.post("/{claim_id}/moderator-approve")
async def moderator_approve(
    claim_id: int,
    current_officer: ClaimsOfficer = Depends(get_current_officer),
    db: DBSession = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if claim.status != "moderator_review":
        raise HTTPException(status_code=400, detail=f"Claim is not in moderator_review (current: {claim.status}).")

    # Record action
    action = ModeratorAction(
        claim_id=claim.id,
        officer_id=current_officer.id,
        decision="approved",
    )
    db.add(action)

    # Update status
    claim.status = "auto_approved"

    # Mark moderator assignment as completed
    mod_assignment = db.query(ClaimAssignment).filter(
        ClaimAssignment.claim_id == claim_id,
        ClaimAssignment.assignment_type == "moderator_review",
        ClaimAssignment.status == "pending",
    ).first()
    if mod_assignment:
        mod_assignment.status = "completed"
        mod_assignment.completed_at = datetime.now(timezone.utc)

    # Initiate payout
    payout = Payout(
        claim_id=claim.id,
        amount_cents=settings.MOCK_PAYOUT_AMOUNT_CENTS,
        status="initiated",
        transaction_id=f"TXN-{claim.claim_number}-MOD",
        initiated_at=datetime.utcnow(),
    )
    db.add(payout)
    claim.payout_amount_cents = settings.MOCK_PAYOUT_AMOUNT_CENTS
    claim.payout_transaction_id = payout.transaction_id
    db.commit()

    log_event(db, claim_id, "officer", "moderator_approved", actor_id=current_officer.name, details={"decision": "approved"})

    # Send notification
    user = db.query(User).filter(User.id == claim.user_id).first()
    if user:
        await notify_claim_status(claim, user, "moderator_approved", db)
        log_event(db, claim_id, "agent", "notification_sent", actor_id="notification_agent", details={"template": "moderator_approved"})

    return {"status": "approved", "claim_number": claim.claim_number, "payout_transaction_id": payout.transaction_id}


@router.post("/{claim_id}/moderator-reject")
async def moderator_reject(
    claim_id: int,
    body: RejectBody,
    current_officer: ClaimsOfficer = Depends(get_current_officer),
    db: DBSession = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if claim.status != "moderator_review":
        raise HTTPException(status_code=400, detail=f"Claim is not in moderator_review (current: {claim.status}).")

    action = ModeratorAction(
        claim_id=claim.id,
        officer_id=current_officer.id,
        decision="rejected",
        rejection_reason=body.reason,
    )
    db.add(action)
    claim.status = "rejected"

    # Mark moderator assignment as completed
    mod_assignment = db.query(ClaimAssignment).filter(
        ClaimAssignment.claim_id == claim_id,
        ClaimAssignment.assignment_type == "moderator_review",
        ClaimAssignment.status == "pending",
    ).first()
    if mod_assignment:
        mod_assignment.status = "completed"
        mod_assignment.completed_at = datetime.now(timezone.utc)

    db.commit()

    log_event(db, claim_id, "officer", "moderator_rejected", actor_id=current_officer.name, details={"reason": body.reason})

    user = db.query(User).filter(User.id == claim.user_id).first()
    if user:
        await notify_claim_status(claim, user, "moderator_rejected", db, reason=body.reason)
        log_event(db, claim_id, "agent", "notification_sent", actor_id="notification_agent", details={"template": "moderator_rejected"})

    return {"status": "rejected", "claim_number": claim.claim_number, "reason": body.reason}
