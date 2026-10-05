"""
Adjudication Orchestrator: deterministic router.
Runs after detection, triggers notifications and payout based on score thresholds.
"""
from datetime import datetime
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim, User, Payout
from app.agents.scoring_adapter import run_fusion_scoring
from app.agents.notification_agent import notify_claim_status
from app.agents.audit_logger import log_event
from app.agents.assignment_agent import assign_siu_officers, assign_moderator
from app.agents.similarity_agent import process_claim_similarity
from app.agents.valuation_agent import evaluate_claim_valuation
from app.ws_manager import ws_manager


async def process_claim(claim_id: int, db: DBSession) -> None:
    """Full pipeline: detection → similarity → adjudication → notification → payout."""

    log_event(db, claim_id, "system", "claim_received", details={"status": "processing"})

    # Step 1: Fraud Fusion Scoring (sets fraud_confidence_score and status)
    score = await run_fusion_scoring(claim_id, db)

    # Step 1b: Narrative similarity check
    try:
        sim_score = process_claim_similarity(claim_id, db)
        if sim_score is not None:
            log_event(db, claim_id, "agent", "similarity_checked", actor_id="similarity_agent",
                      details={"narrative_similarity_score": sim_score})
    except Exception as e:
        print(f"[SIMILARITY ERROR] Claim {claim_id}: {e}")

    log_event(db, claim_id, "agent", "detection_completed", actor_id="fusion_scoring_engine", details={
        "fraud_confidence_score": score,
    })

    # Refresh claim after detection updated it
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        return

    user = db.query(User).filter(User.id == claim.user_id).first()
    if not user:
        return

    log_event(db, claim_id, "system", "adjudication_routed", details={
        "score": score,
        "decision": claim.status,
        "threshold_auto_approve": settings.AUTO_APPROVE_BELOW,
        "threshold_siu": settings.SIU_FLAG_ABOVE,
    })

    # Step 2: Route based on status (already set by detection_agent)
    if claim.status == "auto_approved":
        # Detection cleared the claim as genuine — check the declared claim amount
        # against a live market cost estimate for the damaged part before paying out.
        try:
            valuation = await evaluate_claim_valuation(claim, db)
        except Exception as e:
            print(f"[VALUATION ERROR] Claim {claim_id}: {e}")
            valuation = {"method": "valuation_error", "approved_amount_cents": settings.MOCK_PAYOUT_AMOUNT_CENTS}

        approved_amount_cents = valuation.get("approved_amount_cents", settings.MOCK_PAYOUT_AMOUNT_CENTS)

        log_event(db, claim_id, "agent", "claim_amount_validated", actor_id="valuation_agent", details=valuation)

        # Initiate payout
        payout = Payout(
            claim_id=claim.id,
            amount_cents=approved_amount_cents,
            status="initiated",
            transaction_id=f"TXN-{claim.claim_number}-{datetime.utcnow().strftime('%H%M%S')}",
            initiated_at=datetime.utcnow(),
        )
        db.add(payout)
        claim.payout_amount_cents = approved_amount_cents
        claim.payout_transaction_id = payout.transaction_id
        db.commit()

        log_event(db, claim_id, "system", "payout_initiated", details={
            "amount_cents": approved_amount_cents,
            "transaction_id": payout.transaction_id,
        })

        await notify_claim_status(claim, user, "auto_approved", db)
        log_event(db, claim_id, "agent", "notification_sent", actor_id="notification_agent", details={"template": "auto_approved"})

    elif claim.status == "moderator_review":
        officer_id = assign_moderator(claim.id, db)
        log_event(db, claim_id, "system", "moderator_assigned", details={"officer_id": officer_id})
        await notify_claim_status(claim, user, "moderator_review", db)
        log_event(db, claim_id, "agent", "notification_sent", actor_id="notification_agent", details={"template": "moderator_review"})

    elif claim.status == "siu_investigation":
        assigned_ids = assign_siu_officers(claim.id, db)
        log_event(db, claim_id, "system", "siu_officers_assigned", details={"officer_ids": assigned_ids, "count": len(assigned_ids)})
        await notify_claim_status(claim, user, "siu_investigation", db)
        log_event(db, claim_id, "agent", "notification_sent", actor_id="notification_agent", details={"template": "siu_investigation"})

    # Broadcast updates via WebSocket
    ws_payload = {
        "type": "claim_update",
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "status": claim.status,
        "fraud_confidence_score": claim.fraud_confidence_score,
        "claimant_name": user.full_name,
    }
    await ws_manager.broadcast_claim_update(claim.id, ws_payload)
    await ws_manager.broadcast_officer_feed(ws_payload)
