"""
Shared fixtures for all test modules.
Uses an isolated in-memory SQLite database — never touches claims.db.
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    User, Policy, Coverage, OTPCode, Session, ClaimsOfficer, Claim, ClaimMediaAnalysis
)

# ── In-memory DB ──────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # all connections share the same in-memory DB
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Fresh in-memory DB per test function."""
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """FastAPI TestClient wired to the test DB."""
    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Seed helpers ──────────────────────────────────────────────────────────────

@pytest.fixture()
def test_user(db) -> User:
    user = User(full_name="Test User", email="test@example.com", phone="9999999999")
    db.add(user)
    db.commit()
    db.refresh(user)

    policy = Policy(user_id=user.id, policy_number="POL-TEST-001", status="active")
    db.add(policy)
    db.commit()
    db.refresh(policy)

    coverage = Coverage(
        policy_id=policy.id,
        coverage_type="comprehensive",
        coverage_label="Comprehensive Cover",
        coverage_limit_cents=500000,
        status="active",
    )
    db.add(coverage)
    db.commit()
    db.refresh(coverage)

    user._policy = policy
    user._coverage = coverage
    return user


@pytest.fixture()
def test_officer(db) -> ClaimsOfficer:
    # dashboard_login compares password_hash directly to the submitted password
    officer = ClaimsOfficer(
        name="Officer One",
        email="officer@test.com",
        password_hash="testpass123",
        role="moderator",
    )
    db.add(officer)
    db.commit()
    db.refresh(officer)
    return officer


@pytest.fixture()
def officer_token(db, test_officer, client) -> str:
    """Login as officer and return session token."""
    resp = client.post("/auth/dashboard-login", json={
        "email": test_officer.email,
        "password": "testpass123",
    })
    return resp.json().get("token", "")


@pytest.fixture()
def user_session(db, test_user) -> str:
    """Create an active session token for the test user."""
    import secrets
    token = secrets.token_hex(32)
    session = Session(
        token=token,
        user_id=test_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=12),
    )
    db.add(session)
    db.commit()
    return token


@pytest.fixture()
def test_claim(db, test_user) -> Claim:
    coverage = test_user._coverage
    claim = Claim(
        claim_number="CLM-2026-TEST01",
        user_id=test_user.id,
        policy_id=test_user._policy.id,
        coverage_id=coverage.id,
        accident_location="Test Location",
        accident_description="Rear-end collision at traffic light",
        audio_url="CLM-2026-TEST01/audio.wav",
        image_url="CLM-2026-TEST01/photo.jpg",
        status="flagged",
        fraud_confidence_score=72.5,
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim


@pytest.fixture()
def test_claim_with_report(db, test_claim) -> Claim:
    test_claim.artifact_report = json.dumps({
        "fraud_confidence_score": 72.5,
        "summary": "High confidence synthetic audio detected.",
        "recommendation": "Refer to SIU for investigation.",
        "modality_reports": [
            {"modality": "audio", "raw_score": 78.0, "verdict": "FAKE", "severity": "high",
             "explanation": "Voice clone detected.", "provider": "mock", "findings": []},
            {"modality": "image", "raw_score": 65.0, "verdict": "SUSPICIOUS", "severity": "medium",
             "explanation": "GAN artifacts present.", "provider": "mock", "findings": []},
        ],
    })
    db.commit()
    db.refresh(test_claim)
    return test_claim
