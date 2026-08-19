"""
Efficiency endpoints: officer workload and performance metrics.
Combines moderator review + SIU vote data for holistic workload balancing.
Also includes notification retry and audit trail endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func

from app.database import get_db
from app.models import ClaimsOfficer, ClaimAssignment, ModeratorAction, SIUOfficerVote, Claim, NotificationLog, AuditTrail

router = APIRouter(prefix="/efficiency", tags=["efficiency"])


def _officer_stats(o: ClaimsOfficer, db: DBSession) -> dict:
    pending = db.query(func.count(ClaimAssignment.id)).filter(
        ClaimAssignment.officer_id == o.id,
        ClaimAssignment.status == "pending",
    ).scalar() or 0

    completed = db.query(func.count(ClaimAssignment.id)).filter(
        ClaimAssignment.officer_id == o.id,
        ClaimAssignment.status == "completed",
    ).scalar() or 0

    # Moderator decisions breakdown
    mod_approved = db.query(func.count(ModeratorAction.id)).filter(
        ModeratorAction.officer_id == o.id,
        ModeratorAction.decision == "approved",
    ).scalar() or 0
    mod_rejected = db.query(func.count(ModeratorAction.id)).filter(
        ModeratorAction.officer_id == o.id,
        ModeratorAction.decision == "rejected",
    ).scalar() or 0

    # SIU votes breakdown
    siu_fraud = db.query(func.count(SIUOfficerVote.id)).filter(
        SIUOfficerVote.officer_id == o.id,
        SIUOfficerVote.vote == "confirm_fraud",
    ).scalar() or 0
    siu_clear = db.query(func.count(SIUOfficerVote.id)).filter(
        SIUOfficerVote.officer_id == o.id,
        SIUOfficerVote.vote == "clear",
    ).scalar() or 0

    total_actions = mod_approved + mod_rejected + siu_fraud + siu_clear
    total_work = pending + completed

    return {
        "id": o.id,
        "name": o.name,
        "email": o.email,
        "role": o.role,
        "department": o.department,
        "pending_assignments": pending,
        "completed_assignments": completed,
        "moderator_approved": mod_approved,
        "moderator_rejected": mod_rejected,
        "siu_fraud_votes": siu_fraud,
        "siu_clear_votes": siu_clear,
        "total_decisions": total_actions,
        "utilization": round(pending / max(total_work, 1) * 100, 1),
    }


@router.get("/officers")
def get_all_officers(db: DBSession = Depends(get_db)):
    officers = db.query(ClaimsOfficer).all()
    return [_officer_stats(o, db) for o in officers]


@router.get("/workload-summary")
def get_workload_summary(db: DBSession = Depends(get_db)):
    officers = db.query(ClaimsOfficer).all()
    stats = [_officer_stats(o, db) for o in officers]

    total_pending = sum(s["pending_assignments"] for s in stats)
    total_completed = sum(s["completed_assignments"] for s in stats)
    total_decisions = sum(s["total_decisions"] for s in stats)

    officer_loads = [{"name": s["name"], "pending": s["pending_assignments"], "role": s["role"]} for s in stats]
    pending_vals = [s["pending_assignments"] for s in stats]
    max_load = max(pending_vals, default=0)
    min_load = min(pending_vals, default=0)

    return {
        "total_officers": len(officers),
        "total_pending_assignments": total_pending,
        "total_completed_assignments": total_completed,
        "total_decisions_made": total_decisions,
        "max_officer_load": max_load,
        "min_officer_load": min_load,
        "load_balance_score": round(100 - (max_load - min_load) * 10, 1) if officers else 100,
        "officer_loads": officer_loads,
    }


@router.get("/officer/{officer_id}/assignments")
def get_officer_assignments(officer_id: int, db: DBSession = Depends(get_db)):
    officer = db.query(ClaimsOfficer).filter(ClaimsOfficer.id == officer_id).first()
    if not officer:
        raise HTTPException(status_code=404, detail="Officer not found.")

    assignments = db.query(ClaimAssignment).filter(
        ClaimAssignment.officer_id == officer_id,
    ).order_by(ClaimAssignment.assigned_at.desc()).all()

    result = []
    for a in assignments:
        claim = db.query(Claim).filter(Claim.id == a.claim_id).first()
        result.append({
            "id": a.id,
            "claim_id": a.claim_id,
            "claim_number": claim.claim_number if claim else "Unknown",
            "claim_status": claim.status if claim else "unknown",
            "fraud_score": claim.fraud_confidence_score if claim else None,
            "assignment_type": a.assignment_type,
            "status": a.status,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        })

    return {
        "officer": _officer_stats(officer, db),
        "assignments": result,
    }


@router.post("/retry-notifications")
async def retry_notifications(db: DBSession = Depends(get_db)):
    """Retry all failed notifications."""
    from app.agents.notification_agent import retry_failed_notifications
    result = await retry_failed_notifications(db)
    return result


@router.get("/failed-notifications")
def get_failed_notifications(db: DBSession = Depends(get_db)):
    """List all failed notification attempts."""
    failed = db.query(NotificationLog).filter(
        NotificationLog.status.in_(["failed", "retry_failed"])
    ).order_by(NotificationLog.sent_at.desc()).all()

    return [
        {
            "id": n.id,
            "claim_id": n.claim_id,
            "channel": n.channel,
            "recipient": n.recipient,
            "template_type": n.template_type,
            "status": n.status,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        }
        for n in failed
    ]


@router.get("/audit-log")
def get_full_audit_log(limit: int = 100, db: DBSession = Depends(get_db)):
    """Get the most recent audit trail entries across all claims."""
    entries = db.query(AuditTrail).order_by(AuditTrail.created_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "claim_id": e.claim_id,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "action": e.action,
            "details_json": e.details_json,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
