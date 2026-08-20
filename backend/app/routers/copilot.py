"""
Copilot chat endpoints: officer <-> AI conversation scoped per claim.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import CopilotMessage
from app.agents.copilot_agent import copilot_respond
from app.agents.audit_logger import log_event

router = APIRouter(prefix="/claims", tags=["copilot"])


class ChatRequest(BaseModel):
    officer_id: int
    message: str


@router.post("/{claim_id}/copilot-chat")
async def copilot_chat(claim_id: int, body: ChatRequest, db: DBSession = Depends(get_db)):
    response = await copilot_respond(claim_id, body.officer_id, body.message, db)
    log_event(db, claim_id, "officer", "copilot_query", actor_id=str(body.officer_id),
              details={"question": body.message[:100], "response_length": len(response)})
    return {"claim_id": claim_id, "role": "assistant", "content": response, "response": response}


@router.get("/{claim_id}/copilot-history")
def copilot_history(claim_id: int, db: DBSession = Depends(get_db)):
    messages = db.query(CopilotMessage).filter(
        CopilotMessage.claim_id == claim_id,
    ).order_by(CopilotMessage.created_at.asc()).all()

    return [
        {
            "role": m.role,
            "content": m.content,
            "officer_id": m.officer_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]
