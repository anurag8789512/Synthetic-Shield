import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import or_

from app.database import get_db
from app.models import User, OTPCode, Session, ClaimsOfficer
from app.schemas import (
    OTPRequest, OTPResponse, OTPVerify, OTPVerifyResponse,
    DashboardLoginRequest, DashboardLoginResponse,
)
from app.config import settings
from app.providers.otp_provider import generate_otp, send_otp, send_otp_async, otp_expiry
from app.agents.audit_logger import log_event

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp", response_model=OTPResponse)
async def request_otp(body: OTPRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(
        or_(User.email == body.identifier, User.phone == body.identifier)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="No policyholder found with these details.")

    code = generate_otp()
    otp = OTPCode(
        identifier=body.identifier,
        code=code,
        expires_at=otp_expiry(),
    )
    db.add(otp)
    db.commit()

    sent, actual_code = await send_otp_async(body.identifier, code)

    # If 2Factor generated its own OTP, update our stored code to match
    if actual_code != code:
        otp.code = actual_code
        db.commit()

    debug_otp = None if sent else code
    return OTPResponse(message="Verification code sent." if sent else "Code generated (check below — delivery failed).", debug_otp=debug_otp)


@router.post("/verify-otp", response_model=OTPVerifyResponse)
def verify_otp(body: OTPVerify, db: DBSession = Depends(get_db)):
    otp = (
        db.query(OTPCode)
        .filter(OTPCode.identifier == body.identifier, OTPCode.verified == False)
        .order_by(OTPCode.created_at.desc())
        .first()
    )

    if not otp:
        raise HTTPException(status_code=400, detail="No pending verification found.")

    if otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")

    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many attempts. Please request a new code.")

    if otp.code != body.code:
        otp.attempts += 1
        db.commit()
        remaining = settings.OTP_MAX_ATTEMPTS - otp.attempts
        raise HTTPException(status_code=400, detail=f"Invalid code. {remaining} attempts remaining.")

    otp.verified = True
    db.commit()

    user = db.query(User).filter(
        or_(User.email == body.identifier, User.phone == body.identifier)
    ).first()

    token = secrets.token_urlsafe(32)
    session = Session(
        token=token,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS),
    )
    db.add(session)
    db.commit()

    return OTPVerifyResponse(session_token=token, user_id=user.id, full_name=user.full_name)


@router.post("/dashboard-login", response_model=DashboardLoginResponse)
def dashboard_login(body: DashboardLoginRequest, db: DBSession = Depends(get_db)):
    """Simple credential check for SIU dashboard officers."""
    officer = db.query(ClaimsOfficer).filter(ClaimsOfficer.email == body.email).first()

    if not officer or officer.password_hash != body.password:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = secrets.token_urlsafe(32)
    session = Session(
        token=token,
        user_id=officer.id,
        expires_at=datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS),
    )
    db.add(session)
    db.commit()

    return DashboardLoginResponse(
        session_token=token,
        officer_id=officer.id,
        name=officer.name,
        role=officer.role,
    )
