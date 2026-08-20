"""Tests for the LLM report synthesizer."""
import json
import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from app.agents.report_synthesizer import synthesize_report


SAMPLE_REPORT = {
    "fraud_confidence_score": 72.5,
    "summary": "Template summary.",
    "recommendation": "Template recommendation.",
    "modality_reports": [
        {"modality": "audio", "raw_score": 78.0, "verdict": "FAKE", "severity": "high",
         "explanation": "template explanation", "provider": "mock", "findings": []},
        {"modality": "image", "raw_score": 65.0, "verdict": "SUSPICIOUS", "severity": "medium",
         "explanation": "template explanation", "provider": "mock", "findings": []},
    ],
}

LLM_NARRATIVE = {
    "summary": "LLM-written overall assessment.",
    "recommendation": "LLM-written recommendation.",
    "modality_explanations": {
        "audio": "LLM audio explanation.",
        "image": "LLM image explanation.",
    },
}


# ── No LLM configured ─────────────────────────────────────────────────────────

def test_synthesize_returns_unchanged_when_llm_unavailable():
    import copy
    original = copy.deepcopy(SAMPLE_REPORT)
    with patch("app.agents.report_synthesizer.llm_available", return_value=False):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["summary"] == original["summary"]
    assert result.get("narrative_source") is None


# ── Successful LLM enrichment ─────────────────────────────────────────────────

def test_synthesize_enriches_summary_from_llm():
    import copy
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": json.dumps(LLM_NARRATIVE)}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["summary"] == "LLM-written overall assessment."


def test_synthesize_enriches_recommendation_from_llm():
    import copy
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": json.dumps(LLM_NARRATIVE)}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["recommendation"] == "LLM-written recommendation."


def test_synthesize_sets_narrative_source_to_llm():
    import copy
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": json.dumps(LLM_NARRATIVE)}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["narrative_source"] == "llm"


def test_synthesize_writes_per_modality_explanations():
    import copy
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": json.dumps(LLM_NARRATIVE)}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    audio_mod = next(m for m in result["modality_reports"] if m["modality"] == "audio")
    assert audio_mod["explanation"] == "LLM audio explanation."


# ── LLM strips markdown code fence ───────────────────────────────────────────

def test_synthesize_handles_markdown_code_fence():
    import copy
    fenced = f"```json\n{json.dumps(LLM_NARRATIVE)}\n```"
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": fenced}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["summary"] == "LLM-written overall assessment."


# ── Graceful fallback on failure ──────────────────────────────────────────────

def test_synthesize_falls_back_on_json_decode_error():
    """Malformed LLM JSON → report returned unchanged."""
    import copy
    original = copy.deepcopy(SAMPLE_REPORT)
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": "this is not json"}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["summary"] == original["summary"]
    assert result.get("narrative_source") is None


def test_synthesize_falls_back_on_llm_exception():
    """LLM raises → report returned unchanged."""
    import copy
    from app.providers.llm_provider import LLMUnavailable
    original = copy.deepcopy(SAMPLE_REPORT)
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               side_effect=LLMUnavailable("no key")):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    assert result["summary"] == original["summary"]


def test_synthesize_preserves_unchanged_fields():
    """Fields not touched by LLM (raw scores, findings) stay intact."""
    import copy
    with patch("app.agents.report_synthesizer.llm_available", return_value=True), \
         patch("app.agents.report_synthesizer.chat", new_callable=AsyncMock,
               return_value={"content": json.dumps(LLM_NARRATIVE)}):
        result = asyncio.run(synthesize_report(copy.deepcopy(SAMPLE_REPORT)))
    audio_mod = next(m for m in result["modality_reports"] if m["modality"] == "audio")
    assert audio_mod["raw_score"] == 78.0
    assert audio_mod["verdict"] == "FAKE"
