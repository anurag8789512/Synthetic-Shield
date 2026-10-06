"""
Assignment Agent: distributes claims to officers based on total workload.
Considers ALL pending work (both moderator reviews and SIU votes) when balancing.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func

from app.models import ClaimsOfficer, ClaimAssignment, ModeratorAction, SIUOfficerVote


def _get_officer_workload(officer_id: int, db: DBSession) -> dict:
    """Get combined workload metrics for an officer across all work types."""
    pending_all = db.query(func.count(ClaimAssignment.id)).filter(
        ClaimAssignment.officer_id == officer_id,
        ClaimAssignment.status == "pending",
    ).scalar() or 0

    completed_all = db.query(func.count(ClaimAssignment.id)).filter(
        ClaimAssignment.officer_id == officer_id,
        ClaimAssignment.status == "completed",
    ).scalar() or 0

    total_moderations = db.query(func.count(ModeratorAction.id)).filter(
        ModeratorAction.officer_id == officer_id,
    ).scalar() or 0

    total_votes = db.query(func.count(SIUOfficerVote.id)).filter(
        SIUOfficerVote.officer_id == officer_id,
    ).scalar() or 0

    return {
        "pending": pending_all,
        "completed": completed_all,
        "total_actions": total_moderations + total_votes,
    }


def assign_siu_officers(claim_id: int, db: DBSession) -> list[int]:
    """Assign up to 5 SIU-eligible officers to a claim, least total-pending first.
    Moderators are never put on an SIU panel; with fewer than 5 eligible officers
    the panel is smaller and the majority threshold adapts (siu.py::_majority)."""
    siu_officers = db.query(ClaimsOfficer).filter(
        ClaimsOfficer.role.in_(["siu_officer", "senior"]),
    ).all()

    # Rank by total pending work (not just SIU, all assignment types)
    officer_loads = [(o, _get_officer_workload(o.id, db)["pending"]) for o in siu_officers]
    officer_loads.sort(key=lambda x: x[1])
    selected = [o for o, _ in officer_loads[:5]]

    assigned_ids = []
    for officer in selected:
        assignment = ClaimAssignment(
            claim_id=claim_id,
            officer_id=officer.id,
            assignment_type="siu_vote",
            status="pending",
            assigned_at=datetime.now(timezone.utc),
        )
        db.add(assignment)
        assigned_ids.append(officer.id)

    db.commit()
    return assigned_ids


def assign_moderator(claim_id: int, db: DBSession) -> int | None:
    """Assign the least total-loaded moderator/senior to a claim."""
    moderators = db.query(ClaimsOfficer).filter(
        ClaimsOfficer.role.in_(["moderator", "senior"]),
    ).all()

    if not moderators:
        return None

    # Rank by total pending work across ALL types
    officer_loads = [(o, _get_officer_workload(o.id, db)["pending"]) for o in moderators]
    selected = min(officer_loads, key=lambda x: x[1])[0]

    assignment = ClaimAssignment(
        claim_id=claim_id,
        officer_id=selected.id,
        assignment_type="moderator_review",
        status="pending",
        assigned_at=datetime.now(timezone.utc),
    )
    db.add(assignment)
    db.commit()
    return selected.id
