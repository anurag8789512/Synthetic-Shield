"""
Audit logger: records every significant claim lifecycle event.
Append-only — never update or delete rows.
"""
from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session as DBSession

from app.models import AuditTrail


def log_event(
    db: DBSession,
    claim_id: int,
    actor_type: str,
    action: str,
    actor_id: str = "",
    details: dict | None = None,
) -> None:
    entry = AuditTrail(
        claim_id=claim_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        details_json=json.dumps(details) if details else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
