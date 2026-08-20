"""Tests for Copilot tools (evidence summary + repair cost lookup)."""
import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.agents.copilot_tools import get_claim_evidence_summary, search_repair_cost_estimate
from app.models import ClaimMediaAnalysis


# ── get_claim_evidence_summary ────────────────────────────────────────────────

def test_summary_returns_error_for_missing_claim(db):
    result = get_claim_evidence_summary(9999, db)
    assert "error" in result
    assert result["error"] == "Claim not found."


def test_summary_returns_correct_claim_fields(db, test_claim):
    result = get_claim_evidence_summary(test_claim.id, db)
    assert result["claim_number"] == test_claim.claim_number
    assert result["status"] == test_claim.status
    assert result["fraud_confidence_score"] == test_claim.fraud_confidence_score
    assert result["accident_description"] == test_claim.accident_description


def test_summary_includes_modality_analysis(db, test_claim):
    analysis = ClaimMediaAnalysis(
        claim_id=test_claim.id,
        modality="audio",
        provider="mock",
        raw_score=78.0,
        findings_json=json.dumps({"findings": [{"detail": "Voice clone detected"}]}),
    )
    db.add(analysis)
    db.commit()

    result = get_claim_evidence_summary(test_claim.id, db)
    assert len(result["per_modality_analysis"]) == 1
    audio = result["per_modality_analysis"][0]
    assert audio["modality"] == "audio"
    assert audio["raw_score"] == 78.0
    assert "Voice clone detected" in audio["findings"]


def test_summary_includes_artifact_report_fields(db, test_claim_with_report):
    result = get_claim_evidence_summary(test_claim_with_report.id, db)
    assert result["artifact_report_summary"] == "High confidence synthetic audio detected."
    assert result["artifact_report_recommendation"] == "Refer to SIU for investigation."


def test_summary_handles_malformed_findings_json(db, test_claim):
    analysis = ClaimMediaAnalysis(
        claim_id=test_claim.id,
        modality="video",
        provider="mock",
        raw_score=55.0,
        findings_json="not valid json{{",
    )
    db.add(analysis)
    db.commit()

    result = get_claim_evidence_summary(test_claim.id, db)
    # Should not crash; findings will be empty
    assert result["per_modality_analysis"][0]["findings"] == []


def test_summary_returns_payout_fields(db, test_claim):
    test_claim.payout_amount_cents = 125000
    test_claim.payout_transaction_id = "TXN-TEST-001"
    db.commit()

    result = get_claim_evidence_summary(test_claim.id, db)
    assert result["payout_amount_cents"] == 125000
    assert result["payout_transaction_id"] == "TXN-TEST-001"


# ── search_repair_cost_estimate ───────────────────────────────────────────────

def test_repair_cost_returns_unavailable_when_no_key():
    with patch("app.agents.copilot_tools.settings") as mock_settings:
        mock_settings.SERPAPI_API_KEY = ""
        result = asyncio.run(search_repair_cost_estimate("rear bumper", "Toyota Corolla 2020"))
    assert result["confidence"] == "unavailable"
    assert "error" in result


def test_repair_cost_returns_error_on_api_failure():
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("app.config.settings") as mock_settings:
        mock_settings.SERPAPI_API_KEY = "test_key"
        mock_settings.MISTRAL_API_KEY = ""
        mock_settings.COPILOT_LLM_PROVIDER = "mock"
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(
                search_repair_cost_estimate("front bumper", "Honda Civic 2019")
            )
    assert result["confidence"] == "unavailable"


def test_repair_cost_parses_serpapi_snippets():
    """Successful SerpApi response with cost snippets -> structured result."""
    serpapi_response = {
        "organic_results": [
            {"title": "Bumper Repair Cost", "snippet": "Replacing a rear bumper costs $300 to $900"},
            {"title": "Auto Body Costs", "snippet": "Average bumper replacement: $500", "link": "http://example.com"},
        ]
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = serpapi_response

    llm_extraction = json.dumps({
        "estimated_min_cents": 30000,
        "estimated_max_cents": 90000,
        "confidence": "medium",
        "notes": "Based on 2 sources",
    })

    with patch("app.agents.copilot_tools.settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls, \
         patch("app.providers.llm_provider.chat", new_callable=AsyncMock,
               return_value={"content": llm_extraction}):
        mock_settings.SERPAPI_API_KEY = "test_key"
        mock_settings.MISTRAL_API_KEY = "mistral_key"
        mock_settings.COPILOT_LLM_PROVIDER = "mistral"
        mock_settings.MISTRAL_MODEL = "mistral-small-latest"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(
            search_repair_cost_estimate("rear bumper", "Toyota Camry 2021")
        )

    assert result.get("estimated_min_cents") == 30000
    assert result.get("estimated_max_cents") == 90000
    assert result.get("confidence") == "medium"
