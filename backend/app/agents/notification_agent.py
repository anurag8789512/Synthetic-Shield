"""
Notification Agent: sends email/SMS notifications on claim status changes.
Template-driven, no LLM — just fills in claim details.
"""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime

import httpx
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models import Claim, User, NotificationLog

_executor = ThreadPoolExecutor(max_workers=2)


TEMPLATES = {
    "auto_approved": {
        "subject": "Claim {claim_number} — Approved",
        "body": (
            "Dear {name},\n\n"
            "Your claim {claim_number} has been automatically verified and approved.\n\n"
            "Status: Approved\n"
            "Estimated Payout: ${payout_amount}\n"
            "Payout will be processed within 2 business days.\n\n"
            "— SyntheticShield"
        ),
    },
    "moderator_review": {
        "subject": "Claim {claim_number} — Under Review",
        "body": (
            "Dear {name},\n\n"
            "Your claim {claim_number} is now under moderator review.\n\n"
            "Status: Moderator Review\n"
            "A claims officer will review your submission shortly.\n"
            "You'll be notified once a decision is made.\n\n"
            "— SyntheticShield"
        ),
    },
    "siu_investigation": {
        "subject": "Claim {claim_number} — Under Investigation",
        "body": (
            "Dear {name},\n\n"
            "Your claim {claim_number} has been flagged for further investigation.\n\n"
            "Status: SIU Investigation\n"
            "A specialist investigator will contact you within 1 business day.\n"
            "Please do not alter or delete any submitted media.\n\n"
            "— SyntheticShield"
        ),
    },
    "moderator_approved": {
        "subject": "Claim {claim_number} — Approved by Reviewer",
        "body": (
            "Dear {name},\n\n"
            "Your claim {claim_number} has been reviewed and approved.\n\n"
            "Status: Approved\n"
            "Estimated Payout: ${payout_amount}\n"
            "Payout will be processed within 2 business days.\n\n"
            "— SyntheticShield"
        ),
    },
    "moderator_rejected": {
        "subject": "Claim {claim_number} — Claim Denied",
        "body": (
            "Dear {name},\n\n"
            "Your claim {claim_number} has been reviewed and denied.\n\n"
            "Status: Rejected\n"
            "Reason: {reason}\n\n"
            "If you believe this is an error, you may submit a re-appeal.\n\n"
            "— SyntheticShield"
        ),
    },
    "siu_confirmed_fraud": {
        "subject": "Claim {claim_number} — Fraud Confirmed",
        "body": (
            "Dear {name},\n\n"
            "Following investigation, your claim {claim_number} has been denied.\n\n"
            "Status: Fraud Confirmed\n"
            "This decision is final. Further action may be taken.\n\n"
            "— SyntheticShield"
        ),
    },
    "siu_cleared": {
        "subject": "Claim {claim_number} — Cleared",
        "body": (
            "Dear {name},\n\n"
            "Your claim {claim_number} has been cleared following investigation.\n\n"
            "Status: Cleared\n"
            "Payout will be processed within 2 business days.\n\n"
            "— SyntheticShield"
        ),
    },
}


def _send_email_notification(to_email: str, subject: str, body: str) -> bool:
    """Send notification email via Resend."""
    if not settings.RESEND_API_KEY:
        print(f"[NOTIFY EMAIL] (no key) To: {to_email}, Subject: {subject}")
        return True

    with httpx.Client(timeout=10.0, verify=False) as client:
        resp = client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": "SyntheticShield <onboarding@resend.dev>",
                "to": [to_email],
                "subject": subject,
                "html": f"<pre style='font-family:sans-serif;line-height:1.6'>{body}</pre>",
            },
        )
        return resp.status_code == 200


def _send_sms_notification(phone: str, message: str) -> bool:
    """Send notification SMS via 2Factor.in transactional (best effort)."""
    # 2Factor requires DLT templates for transactional; skip for now
    print(f"[NOTIFY SMS] To: {phone}, Message: {message[:80]}...")
    return True


async def notify_claim_status(
    claim: Claim, user: User, template_type: str, db: DBSession, reason: str = ""
) -> None:
    """Send notifications for a claim status change."""
    template = TEMPLATES.get(template_type)
    if not template:
        print(f"[NOTIFY] Unknown template: {template_type}")
        return

    payout_amount = f"{settings.MOCK_PAYOUT_AMOUNT_CENTS / 100:,.2f}"
    params = {
        "name": user.full_name,
        "claim_number": claim.claim_number,
        "payout_amount": payout_amount,
        "reason": reason,
    }

    subject = template["subject"].format(**params)
    body = template["body"].format(**params)

    loop = asyncio.get_event_loop()

    # Send email
    email_sent = False
    if user.email:
        try:
            email_sent = await loop.run_in_executor(
                _executor, _send_email_notification, user.email, subject, body
            )
        except Exception as e:
            print(f"[NOTIFY ERROR] Email to {user.email}: {e}")

    db.add(NotificationLog(
        claim_id=claim.id,
        channel="email",
        recipient=user.email or "",
        template_type=template_type,
        status="sent" if email_sent else "failed",
        sent_at=datetime.utcnow(),
    ))

    # Send SMS (best effort)
    sms_sent = False
    if user.phone:
        short_msg = f"SyntheticShield: {subject}"
        try:
            sms_sent = await loop.run_in_executor(
                _executor, _send_sms_notification, user.phone, short_msg
            )
        except Exception as e:
            print(f"[NOTIFY ERROR] SMS to {user.phone}: {e}")

    db.add(NotificationLog(
        claim_id=claim.id,
        channel="sms",
        recipient=user.phone or "",
        template_type=template_type,
        status="sent" if sms_sent else "failed",
        sent_at=datetime.utcnow(),
    ))

    db.commit()


MAX_RETRIES = 3


async def retry_failed_notifications(db: DBSession) -> dict:
    """Retry all failed notifications up to MAX_RETRIES times. Returns summary."""
    failed = db.query(NotificationLog).filter(NotificationLog.status == "failed").all()
    retried = 0
    succeeded = 0
    still_failed = 0

    loop = asyncio.get_event_loop()

    for notif in failed:
        # Count previous attempts for this claim+channel+template combo
        attempt_count = db.query(NotificationLog).filter(
            NotificationLog.claim_id == notif.claim_id,
            NotificationLog.channel == notif.channel,
            NotificationLog.template_type == notif.template_type,
        ).count()

        if attempt_count > MAX_RETRIES:
            still_failed += 1
            continue

        retried += 1
        success = False
        try:
            if notif.channel == "email":
                # Rebuild subject/body from template
                claim = db.query(Claim).filter(Claim.id == notif.claim_id).first()
                template = TEMPLATES.get(notif.template_type)
                if claim and template:
                    user = db.query(User).filter(User.id == claim.user_id).first()
                    if user:
                        payout_amount = f"{settings.MOCK_PAYOUT_AMOUNT_CENTS / 100:,.2f}"
                        params = {"name": user.full_name, "claim_number": claim.claim_number, "payout_amount": payout_amount, "reason": ""}
                        subject = template["subject"].format(**params)
                        body = template["body"].format(**params)
                        success = await loop.run_in_executor(_executor, _send_email_notification, notif.recipient, subject, body)
            elif notif.channel == "sms":
                success = await loop.run_in_executor(_executor, _send_sms_notification, notif.recipient, f"SyntheticShield notification retry")
        except Exception as e:
            print(f"[RETRY ERROR] {notif.channel} to {notif.recipient}: {e}")

        if success:
            notif.status = "sent"
            succeeded += 1
        else:
            # Log a new failed attempt
            db.add(NotificationLog(
                claim_id=notif.claim_id,
                channel=notif.channel,
                recipient=notif.recipient,
                template_type=notif.template_type,
                status="retry_failed",
                sent_at=datetime.utcnow(),
            ))
            still_failed += 1

    db.commit()
    return {"retried": retried, "succeeded": succeeded, "still_failed": still_failed, "total_failed": len(failed)}
