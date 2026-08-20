"""Tests for authentication routes (OTP flow + dashboard login)."""
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest

from app.models import OTPCode, Session, User, ClaimsOfficer
import hashlib


# ── POST /auth/request-otp ────────────────────────────────────────────────────

def test_request_otp_returns_404_for_unknown_user(client):
    resp = client.post("/auth/request-otp", json={"identifier": "unknown@nobody.com"})
    assert resp.status_code == 404


def test_request_otp_returns_200_for_known_email(client, test_user):
    with patch("app.routers.auth.send_otp_async", new_callable=AsyncMock, return_value=(False, "123456")):
        resp = client.post("/auth/request-otp", json={"identifier": test_user.email})
    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body


def test_request_otp_returns_200_for_known_phone(client, test_user):
    with patch("app.routers.auth.send_otp_async", new_callable=AsyncMock, return_value=(False, "654321")):
        resp = client.post("/auth/request-otp", json={"identifier": test_user.phone})
    assert resp.status_code == 200


def test_request_otp_creates_otp_record_in_db(client, db, test_user):
    with patch("app.routers.auth.send_otp_async", new_callable=AsyncMock, return_value=(False, "111222")):
        client.post("/auth/request-otp", json={"identifier": test_user.email})
    otp = db.query(OTPCode).filter(OTPCode.identifier == test_user.email).first()
    assert otp is not None
    assert otp.verified is False


# ── POST /auth/verify-otp ─────────────────────────────────────────────────────

def test_verify_otp_returns_400_for_no_pending_code(client):
    resp = client.post("/auth/verify-otp", json={"identifier": "test@example.com", "code": "000000"})
    assert resp.status_code == 400


def test_verify_otp_returns_400_for_wrong_code(client, db, test_user):
    otp = OTPCode(
        identifier=test_user.email,
        code="123456",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(otp)
    db.commit()

    resp = client.post("/auth/verify-otp", json={"identifier": test_user.email, "code": "999999"})
    assert resp.status_code == 400
    assert "Invalid code" in resp.json()["detail"]


def test_verify_otp_returns_400_for_expired_code(client, db, test_user):
    otp = OTPCode(
        identifier=test_user.email,
        code="123456",
        expires_at=datetime.utcnow() - timedelta(minutes=1),  # already expired
    )
    db.add(otp)
    db.commit()

    resp = client.post("/auth/verify-otp", json={"identifier": test_user.email, "code": "123456"})
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


def test_verify_otp_returns_session_token_on_correct_code(client, db, test_user):
    otp = OTPCode(
        identifier=test_user.email,
        code="123456",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(otp)
    db.commit()

    resp = client.post("/auth/verify-otp", json={"identifier": test_user.email, "code": "123456"})
    assert resp.status_code == 200
    body = resp.json()
    assert "session_token" in body
    assert len(body["session_token"]) > 10


def test_verify_otp_marks_code_as_verified(client, db, test_user):
    otp = OTPCode(
        identifier=test_user.email,
        code="999888",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(otp)
    db.commit()

    client.post("/auth/verify-otp", json={"identifier": test_user.email, "code": "999888"})
    db.refresh(otp)
    assert otp.verified is True


def test_verify_otp_increments_attempts_on_wrong_code(client, db, test_user):
    otp = OTPCode(
        identifier=test_user.email,
        code="123456",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(otp)
    db.commit()

    client.post("/auth/verify-otp", json={"identifier": test_user.email, "code": "000000"})
    db.refresh(otp)
    assert otp.attempts == 1


def test_verify_otp_blocks_after_max_attempts(client, db, test_user):
    otp = OTPCode(
        identifier=test_user.email,
        code="123456",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=5,  # already at max
    )
    db.add(otp)
    db.commit()

    resp = client.post("/auth/verify-otp", json={"identifier": test_user.email, "code": "123456"})
    assert resp.status_code == 400
    assert "Too many attempts" in resp.json()["detail"]


# ── POST /auth/dashboard-login ────────────────────────────────────────────────

def test_dashboard_login_returns_404_for_unknown_officer(client):
    resp = client.post("/auth/dashboard-login", json={
        "email": "nobody@test.com", "password": "wrong"
    })
    assert resp.status_code in (401, 404)


def test_dashboard_login_returns_401_for_wrong_password(client, db):
    officer = ClaimsOfficer(
        name="Test Officer",
        email="login_test@test.com",
        password_hash="correctpass",
        role="moderator",
    )
    db.add(officer)
    db.commit()

    resp = client.post("/auth/dashboard-login", json={
        "email": "login_test@test.com", "password": "wrongpass"
    })
    assert resp.status_code in (401, 403)


def test_dashboard_login_returns_token_on_correct_credentials(client, db):
    officer = ClaimsOfficer(
        name="Test Officer",
        email="valid_officer@test.com",
        password_hash="correctpass",
        role="moderator",
    )
    db.add(officer)
    db.commit()

    resp = client.post("/auth/dashboard-login", json={
        "email": "valid_officer@test.com", "password": "correctpass"
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body or "session_token" in body
