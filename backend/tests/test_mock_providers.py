"""Tests for mock detection providers."""
import pytest
import asyncio

from app.providers.detection.mock_providers import (
    _score_from_seed,
    _apply_overrides,
    analyze_video,
    analyze_audio,
    analyze_image,
    analyze_text,
)


# ── _score_from_seed ──────────────────────────────────────────────────────────

def test_score_from_seed_is_deterministic():
    assert _score_from_seed("test_seed") == _score_from_seed("test_seed")


def test_score_from_seed_range():
    for seed in ["abc", "xyz", "123", "video:file.mp4:1024"]:
        score = _score_from_seed(seed)
        assert 0.0 <= score <= 100.0


def test_score_from_seed_different_seeds_differ():
    assert _score_from_seed("seed_a") != _score_from_seed("seed_b")


# ── _apply_overrides ──────────────────────────────────────────────────────────

def test_apply_overrides_fraud_keyword_forces_high():
    score = _apply_overrides("fraud_video.mp4", 20.0)
    assert score >= 85.1


def test_apply_overrides_fake_keyword_forces_high():
    score = _apply_overrides("fake_audio.wav", 10.0)
    assert score >= 85.1


def test_apply_overrides_clean_keyword_forces_low():
    score = _apply_overrides("clean_photo.jpg", 80.0)
    assert score <= 14.9


def test_apply_overrides_real_keyword_forces_low():
    score = _apply_overrides("real_image.png", 90.0)
    assert score <= 14.9


def test_apply_overrides_no_keyword_returns_base():
    base = 55.0
    assert _apply_overrides("normal_file.mp4", base) == base


# ── analyze_video ─────────────────────────────────────────────────────────────

def test_analyze_video_returns_required_keys():
    result = asyncio.run(analyze_video("test.mp4", b"content"))
    assert "raw_score" in result
    assert "findings" in result
    assert isinstance(result["findings"], list)


def test_analyze_video_score_in_range():
    result = asyncio.run(analyze_video("test.mp4", b"bytes"))
    assert 0.0 <= result["raw_score"] <= 100.0


def test_analyze_video_fraud_filename_high_score():
    result = asyncio.run(analyze_video("fraud_clip.mp4", b"bytes"))
    assert result["raw_score"] >= 85.1
    assert len(result["findings"]) > 0


def test_analyze_video_clean_filename_low_score():
    result = asyncio.run(analyze_video("clean_dashcam.mp4", b"bytes"))
    assert result["raw_score"] <= 14.9


def test_analyze_video_high_score_has_findings():
    result = asyncio.run(analyze_video("fraud_video.mp4", b"bytes"))
    assert len(result["findings"]) >= 2


# ── analyze_audio ─────────────────────────────────────────────────────────────

def test_analyze_audio_returns_required_keys():
    result = asyncio.run(analyze_audio("test.wav", b"content"))
    assert "raw_score" in result
    assert "findings" in result


def test_analyze_audio_score_in_range():
    result = asyncio.run(analyze_audio("statement.wav", b"audio_bytes"))
    assert 0.0 <= result["raw_score"] <= 100.0


def test_analyze_audio_fraud_filename():
    result = asyncio.run(analyze_audio("synthetic_voice.wav", b"data"))
    assert result["raw_score"] >= 85.1


def test_analyze_audio_clean_filename():
    result = asyncio.run(analyze_audio("genuine_statement.wav", b"data"))
    assert result["raw_score"] <= 14.9


# ── analyze_image ─────────────────────────────────────────────────────────────

def test_analyze_image_returns_required_keys():
    result = asyncio.run(analyze_image("photo.jpg", b"content"))
    assert "raw_score" in result
    assert "findings" in result


def test_analyze_image_score_in_range():
    result = asyncio.run(analyze_image("damage.jpg", b"bytes"))
    assert 0.0 <= result["raw_score"] <= 100.0


def test_analyze_image_fake_filename():
    result = asyncio.run(analyze_image("fake_damage.jpg", b"data"))
    assert result["raw_score"] >= 85.1


# ── analyze_text ──────────────────────────────────────────────────────────────

def test_analyze_text_returns_required_keys():
    result = asyncio.run(analyze_text("Normal accident description"))
    assert "raw_score" in result
    assert "findings" in result


def test_analyze_text_score_in_range():
    result = asyncio.run(analyze_text("Car was rear-ended at traffic light"))
    assert 0.0 <= result["raw_score"] <= 100.0
