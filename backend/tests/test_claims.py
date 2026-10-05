"""Tests for claims routes and the copilot chat endpoint."""
import io
import json
from unittest.mock import patch, AsyncMock

import pytest

from app.models import Claim, ClaimMediaAnalysis, CopilotMessage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _multipart_claim(coverage_id: int, **overrides) -> dict:
    """Return a minimal valid multipart payload dict for submit_claim."""
    defaults = {
        "coverage_id": str(coverage_id),
        "accident_location": "Test Street",
        "accident_description": "Car was rear-ended.",
        "claim_amount": "500",
    }
    defaults.update(overrides)
    return defaults


# ── POST /claims — auth guard ─────────────────────────────────────────────────

def test_submit_claim_requires_auth(client):
    resp = client.post("/claims", data={"coverage_id": "1",
                                        "accident_location": "X",
                                        "accident_description": "Y"})
    assert resp.status_code in (401, 403)


# ── POST /claims — validation ─────────────────────────────────────────────────

def test_submit_claim_rejects_missing_audio(client, test_user, user_session):
    data = _multipart_claim(test_user._coverage.id)
    files = {
        "image": ("photo.jpg", b"fake_image_bytes", "image/jpeg"),
    }
    resp = client.post("/claims", data=data, files=files,
                       headers=_auth_headers(user_session))
    assert resp.status_code == 422  # FastAPI validation (audio is required)


def test_submit_claim_rejects_no_visual_evidence(client, test_user, user_session):
    data = _multipart_claim(test_user._coverage.id)
    files = {
        "audio": ("statement.wav", b"fake_audio_bytes", "audio/wav"),
    }
    with patch("app.agents.detection_agent.run_detection", new_callable=AsyncMock, return_value=25.0):
        resp = client.post("/claims", data=data, files=files,
                           headers=_auth_headers(user_session))
    assert resp.status_code == 400
    assert "video or image" in resp.json()["detail"].lower()


def test_submit_claim_rejects_invalid_coverage(client, test_user, user_session):
    data = _multipart_claim(9999)  # non-existent coverage_id
    files = {
        "audio": ("statement.wav", b"audio", "audio/wav"),
        "image": ("photo.jpg", b"image", "image/jpeg"),
    }
    with patch("app.agents.detection_agent.run_detection", new_callable=AsyncMock, return_value=25.0):
        resp = client.post("/claims", data=data, files=files,
                           headers=_auth_headers(user_session))
    assert resp.status_code == 400


def test_submit_claim_rejects_non_pdf_document(client, test_user, user_session):
    data = _multipart_claim(test_user._coverage.id)
    files = {
        "audio": ("statement.wav", b"audio", "audio/wav"),
        "image": ("photo.jpg", b"image", "image/jpeg"),
        "document": ("report.exe", b"binary", "application/octet-stream"),
    }
    with patch("app.agents.detection_agent.run_detection", new_callable=AsyncMock, return_value=25.0):
        resp = client.post("/claims", data=data, files=files,
                           headers=_auth_headers(user_session))
    assert resp.status_code == 400
    assert "pdf" in resp.json()["detail"].lower()


# ── POST /claims — successful submission ─────────────────────────────────────

def test_submit_claim_creates_claim_record(client, db, test_user, user_session):
    data = _multipart_claim(test_user._coverage.id)
    files = {
        "audio": ("statement.wav", b"audio_bytes", "audio/wav"),
        "image": ("damage.jpg", b"image_bytes", "image/jpeg"),
    }
    with patch("app.agents.detection_agent.run_detection", new_callable=AsyncMock, return_value=30.0), \
         patch("app.providers.storage.save_file", return_value="media/test.jpg"):
        resp = client.post("/claims", data=data, files=files,
                           headers=_auth_headers(user_session))
    assert resp.status_code == 200
    body = resp.json()
    assert "claim_number" in body
    assert body["claim_number"].startswith("CLM-")


def test_submit_claim_accepts_both_video_and_image(client, db, test_user, user_session):
    data = _multipart_claim(test_user._coverage.id)
    files = {
        "audio": ("statement.wav", b"audio_bytes", "audio/wav"),
        "video": ("dashcam.mp4", b"video_bytes", "video/mp4"),
        "image": ("damage.jpg", b"image_bytes", "image/jpeg"),
    }
    with patch("app.agents.detection_agent.run_detection", new_callable=AsyncMock, return_value=20.0), \
         patch("app.providers.storage.save_file", return_value="media/test.file"):
        resp = client.post("/claims", data=data, files=files,
                           headers=_auth_headers(user_session))
    assert resp.status_code == 200


# ── GET /claims/queue/all ─────────────────────────────────────────────────────

def test_get_claims_queue_requires_officer_auth(client, test_claim):
    resp = client.get("/claims/queue/all")
    assert resp.status_code == 401


def test_get_claims_queue_returns_list(client, test_claim, officer_token):
    resp = client.get("/claims/queue/all", headers=_auth_headers(officer_token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_claims_queue_includes_test_claim(client, test_claim, officer_token):
    resp = client.get("/claims/queue/all", headers=_auth_headers(officer_token))
    claim_numbers = [c["claim_number"] for c in resp.json()]
    assert test_claim.claim_number in claim_numbers


# ── POST /claims/{id}/review-done ─────────────────────────────────────────────

def test_review_done_requires_officer_auth(client, test_claim):
    resp = client.post(f"/claims/{test_claim.id}/review-done")
    assert resp.status_code == 401


def test_review_done_rejects_non_auto_approved_claim(client, test_claim, officer_token):
    resp = client.post(f"/claims/{test_claim.id}/review-done", headers=_auth_headers(officer_token))
    assert resp.status_code == 400


def test_review_done_moves_claim_from_queue_to_case_files(client, test_claim, officer_token, db):
    test_claim.status = "auto_approved"
    db.commit()

    # before: pinned in the queue as review-only, attributed to the system
    before = next(c for c in client.get("/claims/queue/all", headers=_auth_headers(officer_token)).json()
                  if c["id"] == test_claim.id)
    assert before["in_queue"] is True and before["queue_action"] == "review_only"

    resp = client.post(f"/claims/{test_claim.id}/review-done", headers=_auth_headers(officer_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "review_done"

    # after: out of the queue, still a system-decided case file
    after = next(c for c in client.get("/claims/queue/all", headers=_auth_headers(officer_token)).json()
                 if c["id"] == test_claim.id)
    assert after["in_queue"] is False
    assert after["in_case_files"] is True
    assert after["decided_by"] == "system"       # NOT reattributed to a moderator
    assert after["moderator_decision"] is None
    assert after["queue_action"] is None

    # acknowledging twice is rejected
    again = client.post(f"/claims/{test_claim.id}/review-done", headers=_auth_headers(officer_token))
    assert again.status_code == 400


# ── GET /claims/{id} — requires user auth ─────────────────────────────────────

def test_get_claim_by_id_returns_correct_claim(client, test_claim, user_session):
    resp = client.get(f"/claims/{test_claim.id}", headers=_auth_headers(user_session))
    assert resp.status_code == 200
    assert resp.json()["claim_number"] == test_claim.claim_number


def test_get_claim_returns_404_for_missing(client, user_session):
    resp = client.get("/claims/99999", headers=_auth_headers(user_session))
    assert resp.status_code == 404


# ── POST /claims/{id}/copilot-chat ────────────────────────────────────────────

def test_copilot_chat_requires_officer_auth(client, test_claim):
    resp = client.post(
        f"/claims/{test_claim.id}/copilot-chat",
        json={"message": "Why was this flagged?"},
    )
    assert resp.status_code == 401


def test_copilot_chat_returns_response(client, test_claim, officer_token):
    with patch("app.routers.copilot.copilot_respond", new_callable=AsyncMock,
               return_value="The fraud score is 72%."):
        resp = client.post(
            f"/claims/{test_claim.id}/copilot-chat",
            json={"message": "Why was this flagged?"},
            headers=_auth_headers(officer_token),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "assistant"
    assert "content" in body or "response" in body


def test_copilot_chat_returns_200_for_missing_claim(client, user_session, officer_token):
    """Copilot endpoint does not validate claim existence — returns 200 with a response."""
    with patch("app.routers.copilot.copilot_respond", new_callable=AsyncMock,
               return_value="I cannot find that claim."):
        resp = client.post(
            "/claims/99999/copilot-chat",
            json={"message": "Hello"},
            headers=_auth_headers(officer_token),
        )
    assert resp.status_code == 200


# ── GET /claims/{id}/copilot-history ─────────────────────────────────────────

def test_copilot_history_returns_empty_list_for_new_claim(client, test_claim, officer_token):
    resp = client.get(f"/claims/{test_claim.id}/copilot-history", headers=_auth_headers(officer_token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_copilot_history_returns_messages_after_chat(client, db, test_claim, officer_token):
    msg = CopilotMessage(
        claim_id=test_claim.id,
        officer_id=1,
        role="officer",
        content="What is the fraud score?",
    )
    db.add(msg)
    db.commit()

    resp = client.get(f"/claims/{test_claim.id}/copilot-history", headers=_auth_headers(officer_token))
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 1
    assert messages[0]["content"] == "What is the fraud score?"
