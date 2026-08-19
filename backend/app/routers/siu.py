"""
SIU endpoints: quorum voting for claims flagged for investigation.
Unanimous 5/5 required to confirm fraud. Any "clear" vote prevents auto-finalization.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Claim, User, SIUReview, SIUOfficerVote, Payout, ClaimAssignment
from app.config import settings
from app.agents.notification_agent import notify_claim_status
from app.agents.audit_logger import log_event

router = APIRouter(prefix="/claims", tags=["siu"])


class VoteBody(BaseModel):
    officer_id: int
    vote: str  # "confirm_fraud" or "clear"
    notes: str = ""


@router.post("/{claim_id}/siu-vote")
async def cast_siu_vote(claim_id: int, body: VoteBody, db: DBSession = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if claim.status != "siu_investigation":
        raise HTTPException(status_code=400, detail=f"Claim is not under SIU investigation (current: {claim.status}).")

    if body.vote not in ("confirm_fraud", "clear"):
        raise HTTPException(status_code=400, detail="Vote must be 'confirm_fraud' or 'clear'.")

    # Get or create SIU review
    review = db.query(SIUReview).filter(SIUReview.claim_id == claim_id).first()
    if not review:
        review = SIUReview(claim_id=claim_id, required_votes=4, status="pending")
        db.add(review)
        db.flush()

    # Check for duplicate vote
    existing = db.query(SIUOfficerVote).filter(
        SIUOfficerVote.siu_review_id == review.id,
        SIUOfficerVote.officer_id == body.officer_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This officer has already voted on this case.")

    # Cast vote
    vote = SIUOfficerVote(
        siu_review_id=review.id,
        officer_id=body.officer_id,
        vote=body.vote,
        notes=body.notes,
    )
    db.add(vote)

    # Mark this officer's assignment as completed
    assignment = db.query(ClaimAssignment).filter(
        ClaimAssignment.claim_id == claim_id,
        ClaimAssignment.officer_id == body.officer_id,
        ClaimAssignment.assignment_type == "siu_vote",
        ClaimAssignment.status == "pending",
    ).first()
    if assignment:
        assignment.status = "completed"
        assignment.completed_at = datetime.now(timezone.utc)

    db.commit()

    log_event(db, claim_id, "officer", "siu_vote_cast", actor_id=str(body.officer_id), details={
        "vote": body.vote, "notes": body.notes,
    })

    # Check if quorum reached
    all_votes = db.query(SIUOfficerVote).filter(SIUOfficerVote.siu_review_id == review.id).all()
    total_cast = len(all_votes)
    fraud_votes = sum(1 for v in all_votes if v.vote == "confirm_fraud")
    clear_votes = sum(1 for v in all_votes if v.vote == "clear")

    result = {"vote_recorded": True, "total_votes": total_cast, "required": review.required_votes, "finalized": False}

    if total_cast >= review.required_votes:
        user = db.query(User).filter(User.id == claim.user_id).first()

        if fraud_votes == review.required_votes:
            # Unanimous fraud
            review.status = "confirmed_fraud"
            claim.status = "siu_confirmed_fraud"
            db.commit()
            log_event(db, claim_id, "system", "siu_finalized", details={"outcome": "confirmed_fraud", "votes": f"{fraud_votes}/{total_cast}"})
            if user:
                await notify_claim_status(claim, user, "siu_confirmed_fraud", db)
            result["finalized"] = True
            result["outcome"] = "confirmed_fraud"
        elif clear_votes > 0:
            # At least one clear vote — case cleared
            review.status = "cleared"
            claim.status = "siu_cleared"
            db.commit()
            log_event(db, claim_id, "system", "siu_finalized", details={"outcome": "cleared", "votes": f"{fraud_votes} fraud / {clear_votes} clear"})

            # Initiate payout for cleared claims
            from datetime import datetime
            payout = Payout(
                claim_id=claim.id,
                amount_cents=settings.MOCK_PAYOUT_AMOUNT_CENTS,
                status="initiated",
                transaction_id=f"TXN-{claim.claim_number}-SIU-CLR",
                initiated_at=datetime.utcnow(),
            )
            db.add(payout)
            claim.payout_amount_cents = settings.MOCK_PAYOUT_AMOUNT_CENTS
            claim.payout_transaction_id = payout.transaction_id
            db.commit()

            if user:
                await notify_claim_status(claim, user, "siu_cleared", db)
            result["finalized"] = True
            result["outcome"] = "cleared"

    return result


@router.get("/{claim_id}/siu-status")
def get_siu_status(claim_id: int, db: DBSession = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")

    review = db.query(SIUReview).filter(SIUReview.claim_id == claim_id).first()
    if not review:
        return {"claim_id": claim_id, "siu_review": None, "message": "No SIU review initiated."}

    votes = db.query(SIUOfficerVote).filter(SIUOfficerVote.siu_review_id == review.id).all()
    return {
        "claim_id": claim_id,
        "claim_number": claim.claim_number,
        "review_status": review.status,
        "required_votes": review.required_votes,
        "votes_cast": len(votes),
        "fraud_votes": sum(1 for v in votes if v.vote == "confirm_fraud"),
        "clear_votes": sum(1 for v in votes if v.vote == "clear"),
        "votes": [
            {"officer_id": v.officer_id, "vote": v.vote, "notes": v.notes, "voted_at": v.voted_at.isoformat() if v.voted_at else None}
            for v in votes
        ],
    }
