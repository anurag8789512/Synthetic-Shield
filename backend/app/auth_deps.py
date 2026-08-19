from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session, User

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: DBSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    session = db.query(Session).filter(Session.token == token).first()

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session token.")
    if session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired.")

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user
