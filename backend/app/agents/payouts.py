"""Payout amount for claims approved by a human (moderator approval or SIU clearance)."""
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim, Coverage


def approved_payout_cents(claim: Claim, db: DBSession) -> int:
    """The claimed amount, capped at the coverage limit. Legacy claims submitted
    without an amount fall back to MOCK_PAYOUT_AMOUNT_CENTS."""
    amount = claim.claim_amount_cents or settings.MOCK_PAYOUT_AMOUNT_CENTS
    coverage = db.query(Coverage).filter(Coverage.id == claim.coverage_id).first()
    if coverage and coverage.coverage_limit_cents:
        amount = min(amount, coverage.coverage_limit_cents)
    return amount
