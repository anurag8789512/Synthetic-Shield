import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func

from app.database import get_db, SessionLocal
from app.models import User, Claim, Coverage, Policy, ClaimDocument, ClaimMediaAnalysis, AuditTrail
from app.auth_deps import get_current_user
from app.providers.storage import save_file

router = APIRouter(prefix="/claims", tags=["claims"])

# Strong reference set to prevent background tasks from being GC'd
_background_tasks: set = set()


def _generate_claim_number(db: DBSession) -> str:
    year = datetime.utcnow().year
    last = db.query(func.max(Claim.id)).scalar() or 0
    return f"CLM-{year}-{str(last + 1).zfill(5)}"


@router.post("")
async def submit_claim(
    coverage_id: int = Form(...),
    accident_location: str = Form(...),
    accident_description: str = Form(...),
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
    document: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    # Validate coverage belongs to the user's policy
    coverage = db.query(Coverage).filter(Coverage.id == coverage_id).first()
    if not coverage:
        raise HTTPException(status_code=400, detail="Invalid coverage_id.")

    policy = db.query(Policy).filter(Policy.id == coverage.policy_id).first()
    if not policy or policy.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Coverage does not belong to your policy.")

    # Validate mandatory files
    if not video or not video.filename:
        raise HTTPException(status_code=400, detail="Video/photo evidence is required.")
    if not audio or not audio.filename:
        raise HTTPException(status_code=400, detail="Audio statement is required.")

    # Validate document is PDF if provided
    if document and document.filename:
        if not document.content_type or "pdf" not in document.content_type.lower():
            if not document.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Document must be a PDF file.")

    claim_number = _generate_claim_number(db)

    # Save media files
    video_content = await video.read()
    video_url = save_file(claim_number, video.filename, video_content)

    audio_content = await audio.read()
    audio_url = save_file(claim_number, audio.filename, audio_content)

    # Create claim record
    claim = Claim(
        claim_number=claim_number,
        user_id=current_user.id,
        policy_id=policy.id,
        coverage_id=coverage_id,
        accident_location=accident_location,
        accident_description=accident_description,
        video_url=video_url,
        audio_url=audio_url,
        status="processing",
    )
    db.add(claim)
    db.flush()

    # Save optional PDF document
    if document and document.filename:
        doc_content = await document.read()
        doc_url = save_file(claim_number, document.filename, doc_content)
        claim_doc = ClaimDocument(
            claim_id=claim.id,
            file_url=doc_url,
            file_type="pdf",
        )
        db.add(claim_doc)

    db.commit()
    db.refresh(claim)

    # Kick off full pipeline in background (strong ref to prevent GC)
    async def _process_claim(claim_id: int):
        from app.agents.orchestrator import process_claim
        detection_db = SessionLocal()
        try:
            await process_claim(claim_id, detection_db)
        except Exception as e:
            print(f"[PIPELINE ERROR] Claim {claim_id}: {e}")
        finally:
            detection_db.close()

    task = asyncio.create_task(_process_claim(claim.id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "message": "Claim submitted successfully. AI analysis in progress.",
    }


@router.get("/queue/all")
def list_all_claims(
    status: Optional[str] = None,
    db: DBSession = Depends(get_db),
):
    """Dashboard endpoint: returns all claims for officers (no auth required for demo)."""
    query = db.query(Claim)
    if status:
        query = query.filter(Claim.status == status)
    claims = query.order_by(Claim.created_at.desc()).all()

    results = []
    for c in claims:
        from app.models import User as UserModel
        user = db.query(UserModel).filter(UserModel.id == c.user_id).first()
        docs = db.query(ClaimDocument).filter(ClaimDocument.claim_id == c.id).all()
        analyses = db.query(ClaimMediaAnalysis).filter(ClaimMediaAnalysis.claim_id == c.id).all()

        results.append({
            "id": c.id,
            "claim_number": c.claim_number,
            "claimant_name": user.full_name if user else "Unknown",
            "status": c.status,
            "accident_location": c.accident_location,
            "accident_description": c.accident_description,
            "video_url": c.video_url,
            "audio_url": c.audio_url,
            "fraud_confidence_score": c.fraud_confidence_score,
            "artifact_report": c.artifact_report,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "documents": [{"id": d.id, "file_url": d.file_url, "file_type": d.file_type} for d in docs],
            "analyses": [
                {"modality": a.modality, "provider": a.provider, "raw_score": a.raw_score, "findings_json": a.findings_json}
                for a in analyses
            ],
            "audit_trail": [
                {"action": a.action, "actor_type": a.actor_type, "actor_id": a.actor_id, "details_json": a.details_json, "created_at": a.created_at.isoformat() if a.created_at else None}
                for a in db.query(AuditTrail).filter(AuditTrail.claim_id == c.id).order_by(AuditTrail.created_at.asc()).all()
            ],
        })
    return results


@router.get("/trail/{claim_id}")
def get_claim_audit_trail(claim_id: int, db: DBSession = Depends(get_db)):
    """Get the full lifecycle flowchart data for a claim."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")

    trail = db.query(AuditTrail).filter(AuditTrail.claim_id == claim_id).order_by(AuditTrail.created_at.asc()).all()
    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "current_status": claim.status,
        "steps": [
            {
                "action": t.action,
                "actor_type": t.actor_type,
                "actor_id": t.actor_id or "",
                "details_json": t.details_json,
                "timestamp": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trail
        ],
    }


@router.get("/report/{claim_id}")
def get_artifact_report(claim_id: int, db: DBSession = Depends(get_db)):
    """Get the full AI explainability report for a claim."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")

    import json
    report = {}
    if claim.artifact_report:
        try:
            report = json.loads(claim.artifact_report)
        except json.JSONDecodeError:
            report = {"raw": claim.artifact_report}

    analyses = db.query(ClaimMediaAnalysis).filter(ClaimMediaAnalysis.claim_id == claim_id).all()

    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "fraud_confidence_score": claim.fraud_confidence_score,
        "report": report,
        "raw_analyses": [
            {
                "modality": a.modality,
                "provider": a.provider,
                "raw_score": a.raw_score,
                "findings": json.loads(a.findings_json) if a.findings_json else {},
            }
            for a in analyses
        ],
    }


@router.get("/report/{claim_id}/pdf")
def download_report_pdf(claim_id: int, db: DBSession = Depends(get_db)):
    """Download the artifact report as a professionally formatted PDF."""
    from fastapi.responses import Response
    from app.report_pdf import generate_report_pdf
    from app.models import Policy, Coverage
    import json as json_mod

    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")

    user = db.query(User).filter(User.id == claim.user_id).first()
    policy = db.query(Policy).filter(Policy.id == claim.policy_id).first()
    coverage = db.query(Coverage).filter(Coverage.id == claim.coverage_id).first() if claim.coverage_id else None

    report = {}
    if claim.artifact_report:
        try:
            report = json_mod.loads(claim.artifact_report)
        except json_mod.JSONDecodeError:
            pass

    claim_dict = {
        "claim_number": claim.claim_number,
        "status": claim.status,
        "fraud_confidence_score": claim.fraud_confidence_score,
        "accident_location": claim.accident_location,
        "accident_description": claim.accident_description,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }
    policy_dict = {
        "policy_number": policy.policy_number if policy else "N/A",
        "status": policy.status if policy else "N/A",
        "coverage_label": coverage.coverage_label if coverage else "Motor",
    }
    user_dict = {
        "full_name": user.full_name if user else "Unknown",
        "email": user.email if user else "",
        "phone": user.phone if user else "",
    }

    pdf_bytes = generate_report_pdf(
        claim=claim_dict,
        policy=policy_dict,
        user=user_dict,
        report=report,
        officer_name="Krishna Anurag",
    )

    filename = f"SyntheticShield_Report_{claim.claim_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/my/list")
def list_claims(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    query = db.query(Claim).filter(Claim.user_id == current_user.id)
    if status:
        query = query.filter(Claim.status == status)
    claims = query.order_by(Claim.created_at.desc()).all()

    return [
        {
            "id": c.id,
            "claim_number": c.claim_number,
            "status": c.status,
            "accident_location": c.accident_location,
            "fraud_confidence_score": c.fraud_confidence_score,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in claims
    ]


@router.get("/{claim_id}")
def get_claim(
    claim_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if claim.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    documents = db.query(ClaimDocument).filter(ClaimDocument.claim_id == claim.id).all()

    return {
        "id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "accident_location": claim.accident_location,
        "accident_description": claim.accident_description,
        "video_url": claim.video_url,
        "audio_url": claim.audio_url,
        "fraud_confidence_score": claim.fraud_confidence_score,
        "consistency_score": claim.consistency_score,
        "artifact_report": claim.artifact_report,
        "coverage_id": claim.coverage_id,
        "policy_id": claim.policy_id,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        "documents": [{"id": d.id, "file_url": d.file_url, "file_type": d.file_type} for d in documents],
    }
