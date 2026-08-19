from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import User, Policy, Coverage
from app.schemas import PolicyOut, CoverageOut
from app.auth_deps import get_current_user

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/me", response_model=list[PolicyOut])
def get_my_policies(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    policies = db.query(Policy).filter(Policy.user_id == current_user.id).all()
    return policies


@router.get("/{policy_id}/coverages", response_model=list[CoverageOut])
def get_policy_coverages(
    policy_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    if policy.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    coverages = db.query(Coverage).filter(Coverage.policy_id == policy_id).all()
    return coverages
