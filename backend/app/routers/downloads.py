"""
Download endpoints for reports, case files, and forensic audit exports.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Claim, User, Policy, Coverage, ClaimMediaAnalysis, AuditTrail
from app.report_generators import generate_report_pdf, generate_case_file_pdf, generate_forensic_audit_pdf

router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.get("/report/{report_id}")
def download_report(report_id: str, title: str = "", report_type: str = "Monthly Digest", date: str = "", pages: int = 10, status: str = "Final"):
    """Download a mock analytics/pattern/summary report as PDF."""
    if not title:
        title = f"Report {report_id}"

    pdf = generate_report_pdf(report_id, title, report_type, date, pages, status)
    filename = f"SyntheticShield_{report_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/case/{case_id}")
def download_case_file(
    case_id: str,
    claim_id: str = "", claimant: str = "", investigator: str = "",
    status: str = "open", score: int = 0, opened: str = "", notes: str = "",
):
    """Download a case file export as PDF."""
    case = {
        "id": case_id, "claimId": claim_id, "claimant": claimant,
        "investigator": investigator, "status": status, "score": score,
        "opened": opened, "notes": notes or "No notes provided.",
    }
    pdf = generate_case_file_pdf(case)
    filename = f"SyntheticShield_{case_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/forensic-audit/{claim_id}")
def download_forensic_audit(claim_id: int, db: DBSession = Depends(get_db)):
    """Download the full forensic audit report for a claim."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")

    user = db.query(User).filter(User.id == claim.user_id).first()
    policy = db.query(Policy).filter(Policy.id == claim.policy_id).first()
    coverage = db.query(Coverage).filter(Coverage.id == claim.coverage_id).first() if claim.coverage_id else None

    analyses = db.query(ClaimMediaAnalysis).filter(ClaimMediaAnalysis.claim_id == claim_id).all()
    trail = db.query(AuditTrail).filter(AuditTrail.claim_id == claim_id).order_by(AuditTrail.created_at.asc()).all()

    claim_data = {
        "claim_number": claim.claim_number, "status": claim.status,
        "fraud_confidence_score": claim.fraud_confidence_score or 0,
        "accident_location": claim.accident_location,
        "accident_description": claim.accident_description,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }
    policy_data = {
        "policy_number": policy.policy_number if policy else "N/A",
        "coverage_label": coverage.coverage_label if coverage else "Motor",
    }
    user_data = {"full_name": user.full_name if user else "Unknown"}

    analyses_data = [
        {"modality": a.modality, "provider": a.provider, "raw_score": a.raw_score, "findings_json": a.findings_json}
        for a in analyses
    ]
    trail_data = [
        {"action": t.action, "actor_type": t.actor_type, "actor_id": t.actor_id,
         "details_json": t.details_json, "created_at": t.created_at.isoformat() if t.created_at else None}
        for t in trail
    ]

    pdf = generate_forensic_audit_pdf(claim_data, policy_data, user_data, analyses_data, trail_data)
    filename = f"SyntheticShield_ForensicAudit_{claim.claim_number}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
