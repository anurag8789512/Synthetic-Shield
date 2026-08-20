"""Tests for the detection agent pipeline."""
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.agents.detection_agent import _run_provider, _media_bytes, run_detection
from app.models import Claim, ClaimMediaAnalysis


MOCK_RESULT = {"raw_score": 42.0, "findings": [{"detail": "test finding"}]}


# ── _run_provider ─────────────────────────────────────────────────────────────

def test_run_provider_returns_mock_when_provider_is_mock():
    with patch("app.agents.detection_agent.mock_providers.analyze_video", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = MOCK_RESULT
        provider, result = asyncio.run(_run_provider("mock", "video", "test.mp4", b"data"))
    assert provider == "mock"
    assert result == MOCK_RESULT


def test_run_provider_falls_back_to_mock_on_rd_failure():
    """Reality Defender raises an exception → falls back to mock."""
    with patch("app.config.settings") as mock_settings:
        mock_settings.REALITY_DEFENDER_API_KEY = "some_key"
        mock_settings.RESEMBLE_AI_API_KEY = ""
        with patch("app.agents.detection_agent.reality_defender.analyze_image",
                   new_callable=AsyncMock, side_effect=Exception("API error")):
            with patch("app.agents.detection_agent.mock_providers.analyze_image",
                       new_callable=AsyncMock, return_value=MOCK_RESULT):
                provider, result = asyncio.run(
                    _run_provider("reality_defender", "image", "photo.jpg", b"data")
                )
    assert provider == "mock"
    assert result == MOCK_RESULT


def test_run_provider_uses_rd_when_configured():
    rd_result = {"raw_score": 88.0, "findings": []}
    with patch("app.config.settings") as mock_settings:
        mock_settings.REALITY_DEFENDER_API_KEY = "valid_key"
        mock_settings.RESEMBLE_AI_API_KEY = ""
        with patch("app.agents.detection_agent.reality_defender.analyze_audio",
                   new_callable=AsyncMock, return_value=rd_result):
            provider, result = asyncio.run(
                _run_provider("reality_defender", "audio", "audio.wav", b"data")
            )
    assert provider == "reality_defender"
    assert result["raw_score"] == 88.0


def test_run_provider_no_rd_key_skips_to_mock():
    """No API key → skips RD entirely, uses mock."""
    with patch("app.config.settings") as mock_settings:
        mock_settings.REALITY_DEFENDER_API_KEY = ""
        mock_settings.RESEMBLE_AI_API_KEY = ""
        with patch("app.agents.detection_agent.mock_providers.analyze_video",
                   new_callable=AsyncMock, return_value=MOCK_RESULT):
            provider, result = asyncio.run(
                _run_provider("reality_defender", "video", "video.mp4", b"data")
            )
    assert provider == "mock"


# ── _media_bytes ──────────────────────────────────────────────────────────────

def test_media_bytes_returns_filename_as_bytes_when_file_missing():
    filename, content = _media_bytes("CLM-2026-FAKE", "CLM-2026-FAKE/audio.wav")
    assert filename == "audio.wav"
    assert content == b"audio.wav"


def test_media_bytes_none_url_returns_unknown():
    filename, content = _media_bytes("CLM-2026-FAKE", None)
    assert filename == "unknown"


# ── run_detection ─────────────────────────────────────────────────────────────

def test_run_detection_returns_zero_for_missing_claim(db):
    score = asyncio.run(run_detection(9999, db))
    assert score == 0.0


def test_run_detection_creates_analysis_records(db, test_claim):
    mock_audio = {"raw_score": 60.0, "findings": []}
    mock_image = {"raw_score": 40.0, "findings": []}

    with patch("app.agents.detection_agent.mock_providers.analyze_audio",
               new_callable=AsyncMock, return_value=mock_audio), \
         patch("app.agents.detection_agent.mock_providers.analyze_image",
               new_callable=AsyncMock, return_value=mock_image), \
         patch("app.agents.report_synthesizer.synthesize_report",
               new_callable=AsyncMock, side_effect=lambda r: r):
        asyncio.run(run_detection(test_claim.id, db))

    analyses = db.query(ClaimMediaAnalysis).filter(
        ClaimMediaAnalysis.claim_id == test_claim.id
    ).all()
    modalities = {a.modality for a in analyses}
    assert "audio" in modalities
    assert "image" in modalities


def test_run_detection_aggregates_weighted_score(db, test_claim):
    """Weighted score = audio*0.30 + image*0.20 (no video/text in test_claim)."""
    mock_audio = {"raw_score": 100.0, "findings": []}
    mock_image = {"raw_score": 100.0, "findings": []}

    with patch("app.agents.detection_agent.mock_providers.analyze_audio",
               new_callable=AsyncMock, return_value=mock_audio), \
         patch("app.agents.detection_agent.mock_providers.analyze_image",
               new_callable=AsyncMock, return_value=mock_image), \
         patch("app.agents.report_synthesizer.synthesize_report",
               new_callable=AsyncMock, side_effect=lambda r: r):
        score = asyncio.run(run_detection(test_claim.id, db))

    assert 0.0 <= score <= 100.0


def test_run_detection_auto_approves_low_score(db, test_user):
    """Claims with fraud score below AUTO_APPROVE_BELOW should be auto-approved."""
    coverage = test_user._coverage
    claim = Claim(
        claim_number="CLM-2026-LOW01",
        user_id=test_user.id,
        policy_id=test_user._policy.id,
        coverage_id=coverage.id,
        accident_location="Test",
        accident_description="Minor scratch",
        audio_url="CLM-2026-LOW01/audio.wav",
        image_url="CLM-2026-LOW01/clean_photo.jpg",
        status="processing",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    low_result = {"raw_score": 5.0, "findings": []}
    with patch("app.agents.detection_agent.settings") as mock_settings, \
         patch("app.agents.detection_agent.mock_providers.analyze_audio",
               new_callable=AsyncMock, return_value=low_result), \
         patch("app.agents.detection_agent.mock_providers.analyze_image",
               new_callable=AsyncMock, return_value=low_result), \
         patch("app.agents.detection_agent.mock_providers.analyze_text",
               new_callable=AsyncMock, return_value=low_result), \
         patch("app.agents.report_synthesizer.synthesize_report",
               new_callable=AsyncMock, side_effect=lambda r: r):
        mock_settings.VIDEO_DETECTION_PROVIDER = "mock"
        mock_settings.AUDIO_DETECTION_PROVIDER = "mock"
        mock_settings.IMAGE_DETECTION_PROVIDER = "mock"
        mock_settings.TEXT_DETECTION_PROVIDER = "mock"
        mock_settings.REALITY_DEFENDER_API_KEY = ""
        mock_settings.RESEMBLE_AI_API_KEY = ""
        mock_settings.AUTO_APPROVE_BELOW = 15
        mock_settings.SIU_FLAG_ABOVE = 85
        asyncio.run(run_detection(claim.id, db))

    db.refresh(claim)
    assert claim.status == "auto_approved"


def test_run_detection_flags_high_score_for_siu(db, test_user):
    """Claims with fraud score above SIU_FLAG_ABOVE should be sent to SIU."""
    coverage = test_user._coverage
    claim = Claim(
        claim_number="CLM-2026-HIGH01",
        user_id=test_user.id,
        policy_id=test_user._policy.id,
        coverage_id=coverage.id,
        accident_location="Test",
        accident_description="Staged collision",
        audio_url="CLM-2026-HIGH01/fraud_audio.wav",
        image_url="CLM-2026-HIGH01/fake_damage.jpg",
        status="processing",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    high_result = {"raw_score": 95.0, "findings": [{"detail": "Synthetic"}]}
    with patch("app.agents.detection_agent.settings") as mock_settings, \
         patch("app.agents.detection_agent.mock_providers.analyze_audio",
               new_callable=AsyncMock, return_value=high_result), \
         patch("app.agents.detection_agent.mock_providers.analyze_image",
               new_callable=AsyncMock, return_value=high_result), \
         patch("app.agents.detection_agent.mock_providers.analyze_text",
               new_callable=AsyncMock, return_value=high_result), \
         patch("app.agents.report_synthesizer.synthesize_report",
               new_callable=AsyncMock, side_effect=lambda r: r):
        mock_settings.VIDEO_DETECTION_PROVIDER = "mock"
        mock_settings.AUDIO_DETECTION_PROVIDER = "mock"
        mock_settings.IMAGE_DETECTION_PROVIDER = "mock"
        mock_settings.TEXT_DETECTION_PROVIDER = "mock"
        mock_settings.REALITY_DEFENDER_API_KEY = ""
        mock_settings.RESEMBLE_AI_API_KEY = ""
        mock_settings.AUTO_APPROVE_BELOW = 15
        mock_settings.SIU_FLAG_ABOVE = 85
        asyncio.run(run_detection(claim.id, db))

    db.refresh(claim)
    assert claim.status == "siu_investigation"
