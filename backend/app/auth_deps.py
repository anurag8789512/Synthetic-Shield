from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session, User, ClaimsOfficer

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: DBSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    session = (
        db.query(Session)
        .filter(Session.token == token, Session.owner_type == "user")
        .first()
    )

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session token.")
    if session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired.")

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


def get_current_officer(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    token: Optional[str] = Query(None, description="Session token (fallback for direct-link downloads)."),
    db: DBSession = Depends(get_db),
) -> ClaimsOfficer:
    """
    Auth guard for dashboard/officer-facing routes. Accepts the token via the
    Authorization header (used by fetch() calls) or a `token` query param
    (used by plain <a href> download links, which can't set headers).
    """
    session_token = credentials.credentials if credentials else token
    if not session_token:
        raise HTTPException(status_code=401, detail="Missing session token.")

    session = (
        db.query(Session)
        .filter(Session.token == session_token, Session.owner_type == "officer")
        .first()
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session token.")
    if session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired.")

    officer = db.query(ClaimsOfficer).filter(ClaimsOfficer.id == session.user_id).first()
    if not officer:
        raise HTTPException(status_code=401, detail="Officer not found.")
    return officer
