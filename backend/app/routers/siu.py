"""
SIU endpoints: majority voting for claims flagged for investigation.
A strict majority of the claim's voting panel (3 of 5) confirms fraud. The case
is cleared as soon as fraud can no longer reach that majority (3 "clear" votes
of 5, or a 2-2 split on a 4-person panel). Either way it finalizes the moment
the outcome is decided; remaining panel members' assignments are closed.

The panel size is derived from the panel itself (see _ballot) rather than
hardcoded, so the officers the dashboard can actually vote as and the number
of votes needed to decide can never disagree.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Claim, User, SIUReview, SIUOfficerVote, Payout, ClaimAssignment, ClaimsOfficer
from app.auth_deps import get_current_officer
from app.agents.notification_agent import notify_claim_status
from app.agents.audit_logger import log_event
from app.agents.payouts import approved_payout_cents

router = APIRouter(prefix="/claims", tags=["siu"])

# Roles eligible for SIU quorum duty — keep in sync with
# agents/assignment_agent.py::assign_siu_officers.
_SIU_ELIGIBLE_ROLES = ("siu_officer", "senior")


class VoteBody(BaseModel):
    officer_id: int
    vote: str  # "confirm_fraud" or "clear"
    notes: str = ""


def _majority(panel_size: int) -> int:
    """Votes needed to confirm fraud: a strict majority of the panel."""
    return panel_size // 2 + 1


def _ballot(claim_id: int, db: DBSession) -> list[ClaimsOfficer]:
    """The officers whose votes make up this claim's quorum.

    Source of truth is the ClaimAssignment rows the assignment agent wrote when
    the claim was routed to SIU. Falls back to every SIU-eligible officer for
    claims whose status was set without going through that agent, so the panel
    is never empty while a claim sits in siu_investigation.
    """
    assigned_ids = [
        a.officer_id
        for a in db.query(ClaimAssignment).filter(
            ClaimAssignment.claim_id == claim_id,
            ClaimAssignment.assignment_type == "siu_vote",
        ).all()
    ]
    if assigned_ids:
        officers = (
            db.query(ClaimsOfficer)
            .filter(ClaimsOfficer.id.in_(assigned_ids))
            .order_by(ClaimsOfficer.id)
            .all()
        )
        if officers:
            return officers
    return (
        db.query(ClaimsOfficer)
        .filter(ClaimsOfficer.role.in_(_SIU_ELIGIBLE_ROLES))
        .order_by(ClaimsOfficer.id)
        .all()
    )


@router.post("/{claim_id}/siu-vote")
async def cast_siu_vote(
    claim_id: int,
    body: VoteBody,
    current_officer: ClaimsOfficer = Depends(get_current_officer),
    db: DBSession = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if claim.status != "siu_investigation":
        raise HTTPException(status_code=400, detail=f"Claim is not under SIU investigation (current: {claim.status}).")

    if body.vote not in ("confirm_fraud", "clear"):
        raise HTTPException(status_code=400, detail="Vote must be 'confirm_fraud' or 'clear'.")

    # A vote may only be attributed to an officer on this claim's panel. The
    # dashboard lets one signed-in officer record the panel's votes, so
    # officer_id is client-supplied by design — but it is never trusted:
    # validate it here and record the real submitter in the audit trail below.
    ballot_ids = {o.id for o in _ballot(claim_id, db)}
    if not ballot_ids:
        raise HTTPException(status_code=400, detail="No SIU officers are available to vote on this claim.")
    if body.officer_id not in ballot_ids:
        raise HTTPException(status_code=400, detail="That officer is not on this claim's SIU voting panel.")

    # Get or create SIU review. Quorum = the size of the panel, so the votes
    # required to finalize always match the votes that can actually be cast.
    # siu_reviews.claim_id is unique: if two first votes race, the loser re-reads
    # the winner's review instead of failing.
    review = db.query(SIUReview).filter(SIUReview.claim_id == claim_id).first()
    if not review:
        try:
            review = SIUReview(claim_id=claim_id, required_votes=len(ballot_ids), status="pending")
            db.add(review)
            db.flush()
        except IntegrityError:
            db.rollback()
            review = db.query(SIUReview).filter(SIUReview.claim_id == claim_id).first()

    # Check for duplicate vote
    existing = db.query(SIUOfficerVote).filter(
        SIUOfficerVote.siu_review_id == review.id,
        SIUOfficerVote.officer_id == body.officer_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This officer has already voted on this case.")

    # Cast vote — the (review, officer) unique constraint also catches a double-click race
    vote = SIUOfficerVote(
        siu_review_id=review.id,
        officer_id=body.officer_id,
        vote=body.vote,
        notes=body.notes,
    )
    db.add(vote)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="This officer has already voted on this case.")

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
        "vote": body.vote,
        "notes": body.notes,
        "vote_attributed_to": body.officer_id,
        # Who was actually signed in when this vote was recorded — without this
        # the trail can't distinguish a panel member's own vote from one
        # recorded on their behalf.
        "submitted_by_officer_id": current_officer.id,
        "submitted_by": current_officer.name,
    })

    # Majority decision: finalize as soon as the outcome can no longer change
    all_votes = db.query(SIUOfficerVote).filter(SIUOfficerVote.siu_review_id == review.id).all()
    total_cast = len(all_votes)
    fraud_votes = sum(1 for v in all_votes if v.vote == "confirm_fraud")
    clear_votes = sum(1 for v in all_votes if v.vote == "clear")
    panel_size = review.required_votes
    majority = _majority(panel_size)

    result = {"vote_recorded": True, "total_votes": total_cast, "required": panel_size,
              "majority_needed": majority, "finalized": False}

    outcome = None
    if fraud_votes >= majority:
        outcome = "confirmed_fraud"
    elif clear_votes > panel_size - majority:  # fraud can no longer reach a majority
        outcome = "cleared"

    # Atomic transition: only the request that moves the claim out of
    # siu_investigation finalizes it, so concurrent votes can't double-finalize
    # (or double-pay a cleared claim).
    if outcome:
        new_status = "siu_confirmed_fraud" if outcome == "confirmed_fraud" else "siu_cleared"
        won = db.execute(
            update(Claim)
            .where(Claim.id == claim_id, Claim.status == "siu_investigation")
            .values(status=new_status)
        ).rowcount == 1
        if not won:
            db.commit()
            db.refresh(claim)
            result.update(finalized=True, outcome=outcome, note="already finalized by a concurrent vote")
            return result
        db.refresh(claim)

    if outcome:
        user = db.query(User).filter(User.id == claim.user_id).first()
        tally = f"{fraud_votes} fraud / {clear_votes} clear of {panel_size} (majority {majority})"
        _close_open_siu_assignments(claim_id, db)

        if outcome == "confirmed_fraud":
            review.status = "confirmed_fraud"
            claim.status = "siu_confirmed_fraud"
            db.commit()
            log_event(db, claim_id, "system", "siu_finalized", details={"outcome": "confirmed_fraud", "votes": tally})
            if user:
                await notify_claim_status(claim, user, "siu_confirmed_fraud", db)
            result["finalized"] = True
            result["outcome"] = "confirmed_fraud"
        else:
            review.status = "cleared"
            claim.status = "siu_cleared"
            db.commit()
            log_event(db, claim_id, "system", "siu_finalized", details={"outcome": "cleared", "votes": tally})

            # Initiate payout for cleared claims: claimed amount, capped at the coverage limit
            amount_cents = approved_payout_cents(claim, db)
            payout = Payout(
                claim_id=claim.id,
                amount_cents=amount_cents,
                status="initiated",
                transaction_id=f"TXN-{claim.claim_number}-SIU-CLR",
                initiated_at=datetime.utcnow(),
            )
            db.add(payout)
            claim.payout_amount_cents = amount_cents
            claim.payout_transaction_id = payout.transaction_id
            db.commit()

            if user:
                await notify_claim_status(claim, user, "siu_cleared", db)
            result["finalized"] = True
            result["outcome"] = "cleared"

    return result


def _close_open_siu_assignments(claim_id: int, db: DBSession) -> None:
    """Panel members who hadn't voted when the majority was reached: their vote can
    no longer change the outcome, so take the claim off their open workload.
    "closed" counts as neither pending nor completed in efficiency stats."""
    for a in db.query(ClaimAssignment).filter(
        ClaimAssignment.claim_id == claim_id,
        ClaimAssignment.assignment_type == "siu_vote",
        ClaimAssignment.status == "pending",
    ).all():
        a.status = "closed"
        a.completed_at = datetime.now(timezone.utc)


@router.get("/{claim_id}/siu-status")
def get_siu_status(
    claim_id: int,
    current_officer: ClaimsOfficer = Depends(get_current_officer),
    db: DBSession = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")

    review = db.query(SIUReview).filter(SIUReview.claim_id == claim_id).first()

    # The review row is created lazily on the first vote, so a claim can sit in
    # siu_investigation with no review yet. Return the full shape either way so
    # the dashboard can render the panel before anyone has voted.
    votes = (
        db.query(SIUOfficerVote).filter(SIUOfficerVote.siu_review_id == review.id).all()
        if review else []
    )
    votes_by_officer = {v.officer_id: v for v in votes}
    ballot = _ballot(claim_id, db)

    return {
        "claim_id": claim_id,
        "claim_number": claim.claim_number,
        "review_status": review.status if review else "pending",
        "required_votes": review.required_votes if review else len(ballot),
        "majority_needed": _majority(review.required_votes if review else len(ballot)),
        "votes_cast": len(votes),
        "fraud_votes": sum(1 for v in votes if v.vote == "confirm_fraud"),
        "clear_votes": sum(1 for v in votes if v.vote == "clear"),
        # This claim's voting panel, with each member's vote if already cast.
        # The dashboard renders exactly these rows, which is what keeps the
        # panel size and required_votes in agreement.
        "panel": [
            {
                "officer_id": o.id,
                "name": o.name,
                "role": o.role,
                "vote": votes_by_officer[o.id].vote if o.id in votes_by_officer else None,
                "notes": votes_by_officer[o.id].notes if o.id in votes_by_officer else None,
                "voted_at": (
                    votes_by_officer[o.id].voted_at.isoformat()
                    if o.id in votes_by_officer and votes_by_officer[o.id].voted_at else None
                ),
            }
            for o in ballot
        ],
        "votes": [
            {"officer_id": v.officer_id, "vote": v.vote, "notes": v.notes, "voted_at": v.voted_at.isoformat() if v.voted_at else None}
            for v in votes
        ],
    }
