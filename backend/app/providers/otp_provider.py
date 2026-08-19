import random
import string
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import httpx
from app.config import settings

_executor = ThreadPoolExecutor(max_workers=2)


def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=settings.OTP_LENGTH))


def _is_email(identifier: str) -> bool:
    return "@" in identifier


def _send_sms_sync(phone: str, code: str) -> str:
    """Send OTP via 2Factor.in AUTOGEN2 (SMS only). Returns the OTP that was sent."""
    with httpx.Client(timeout=10.0, verify=False) as client:
        url = f"https://2factor.in/API/V1/{settings.TWOFACTOR_API_KEY}/SMS/{phone}/AUTOGEN2"
        resp = client.get(url)
        print(f"[2FACTOR] Status: {resp.status_code}, Body: {resp.text[:200]}")
        if resp.status_code != 200:
            raise Exception(f"2Factor.in: {resp.text[:200]}")
        data = resp.json()
        if data.get("Status") != "Success":
            raise Exception(f"2Factor.in rejected: {data.get('Details', 'unknown')}")
        # 2Factor returns the OTP it generated
        return data.get("OTP", code)


def _send_email_sync(email: str, code: str) -> None:
    with httpx.Client(timeout=10.0, verify=False) as client:
        resp = client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": "SyntheticShield <onboarding@resend.dev>",
                "to": [email],
                "subject": f"Your SyntheticShield verification code: {code}",
                "html": (
                    f"<div style='font-family:sans-serif;padding:20px'>"
                    f"<h2>SyntheticShield Verification</h2>"
                    f"<p>Your one-time verification code is:</p>"
                    f"<h1 style='letter-spacing:8px;color:#0284C7'>{code}</h1>"
                    f"<p>This code expires in {settings.OTP_EXPIRY_MINUTES} minutes.</p>"
                    f"<p style='color:#64748B;font-size:12px'>If you didn't request this, ignore this email.</p>"
                    f"</div>"
                ),
            },
        )
        print(f"[RESEND] Status: {resp.status_code}, Body: {resp.text[:200]}")
        if resp.status_code != 200:
            raise Exception(f"Resend: {resp.text[:200]}")


def send_otp(identifier: str, code: str) -> None:
    if settings.OTP_PROVIDER == "console":
        print(f"[OTP CONSOLE] Code for {identifier}: {code}")


async def send_otp_async(identifier: str, code: str) -> tuple[bool, str]:
    """Send OTP. Returns (success, actual_code_sent)."""
    if settings.OTP_PROVIDER == "console":
        print(f"[OTP CONSOLE] Code for {identifier}: {code}")
        return False, code

    loop = asyncio.get_event_loop()
    try:
        if _is_email(identifier):
            if settings.RESEND_API_KEY:
                await loop.run_in_executor(_executor, _send_email_sync, identifier, code)
                return True, code
        else:
            if settings.TWOFACTOR_API_KEY:
                actual_code = await loop.run_in_executor(_executor, _send_sms_sync, identifier, code)
                return True, actual_code
    except Exception as e:
        print(f"[OTP ERROR] {identifier}: {e}")

    return False, code


def otp_expiry() -> datetime:
    return datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
