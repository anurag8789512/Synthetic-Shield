"""Level 1 metadata rules + Level 3 consistency engine tests."""
from datetime import datetime, timedelta

import pytest

from app.scoring.config import get_config
from app.scoring.level1_metadata import exif_rules
from app.scoring.level3_consistency.engine import ConsistencyEngine
from app.scoring.level3_consistency.fact_extraction import extract_facts, zones_conflict
from app.scoring.level3_consistency.part_pricing import MockPartPricingProvider
from app.scoring.level3_consistency.reverse_search import MockReverseSearchProvider
from app.scoring.level3_consistency.weather import MockWeatherProvider

CFG = get_config()
MCFG = CFG.metadata


# ── Metadata rules ────────────────────────────────────────────────────────────
def test_m_h1_editor_trace():
    f = exif_rules.rule_m_h1_editor_trace({"software": "Adobe Photoshop 25.1"}, MCFG, "img.jpg")
    assert f and f.rule_id == "M-H1" and f.points == MCFG.high


def test_m_h1_no_editor():
    assert exif_rules.rule_m_h1_editor_trace({"software": "Apple iOS 17"}, MCFG, "img.jpg") is None


def test_m_h2_gps_contradiction():
    meta = {"gps": (28.61, 77.20)}  # Delhi
    f = exif_rules.rule_m_h2_gps_contradiction(meta, MCFG, "img.jpg", (19.07, 72.87))  # Mumbai
    assert f and f.rule_id == "M-H2"


def test_m_h2_within_radius():
    meta = {"gps": (28.61, 77.20)}
    assert exif_rules.rule_m_h2_gps_contradiction(meta, MCFG, "img.jpg", (28.62, 77.21)) is None


def test_m_h3_future_timestamp():
    future = (datetime.utcnow() + timedelta(days=2)).strftime("%Y:%m:%d %H:%M:%S")
    f = exif_rules.rule_m_h3_impossible_timestamp({"datetime_original": future}, MCFG,
                                                  "img.jpg", datetime.utcnow(), None)
    assert f and f.rule_id == "M-H3"


def test_m_l1_missing_exif_is_weak():
    f = exif_rules.rule_m_l1_missing_exif({"has_exif": False}, MCFG, "img.jpg", False)
    assert f and f.severity == "low" and f.points == MCFG.low == 8


def test_m_l1_skipped_for_in_app_capture():
    assert exif_rules.rule_m_l1_missing_exif({"has_exif": False}, MCFG, "img.jpg", True) is None


def test_m_c2_intact_exif_credit():
    meta = {"make": "Apple", "model": "iPhone 15", "gps": (28.61, 77.20),
            "datetime_original": "2026:09:01 10:00:00"}
    f = exif_rules.rule_m_c2_intact_exif(meta, MCFG, "img.jpg", (28.61, 77.20),
                                         datetime(2026, 9, 2))
    assert f and f.points == MCFG.credits.intact_exif < 0


# ── Fact extraction ───────────────────────────────────────────────────────────
def test_fact_extraction_zones_and_type():
    facts = extract_facts("I was rear-ended and my rear bumper is cracked", "written")
    assert facts.incident_type == "rear_end"
    assert facts.impact_zone == "rear"
    assert "rear_bumper" in facts.damaged_parts


def test_zone_conflict_front_vs_rear():
    assert zones_conflict("front", "rear") is True
    assert zones_conflict("front", "front") is False
    assert zones_conflict("left", "right") is True
    assert zones_conflict(None, "rear") is False


# ── Consistency engine ────────────────────────────────────────────────────────
def _engine():
    return ConsistencyEngine(CFG, MockWeatherProvider(), MockReverseSearchProvider(),
                             MockPartPricingProvider())


@pytest.mark.asyncio
async def test_c_h1_hard_contradiction():
    sub = await _engine().analyze(
        transcript="a car hit the front of the car, the hood is bent",
        written_description="I was hit from behind, the rear bumper and the back of the car are damaged",
        photo_zone=None, incident_dt=None, location=None,
        media_datetime_originals=[], claim_amount=None, vehicle_description="car",
        region="", coverage_limit=None, image_urls_for_external_search=[],
        run_external_search=False,
    )
    assert any(f.rule_id == "C-H1" for f in sub.findings)
    assert sub.value >= 45


@pytest.mark.asyncio
async def test_c_m3_damage_pattern_implausibility():
    sub = await _engine().analyze(
        transcript=None,
        written_description="I was rear ended at a light; my hood and front grill took the damage",
        photo_zone=None, incident_dt=None, location=None,
        media_datetime_originals=[], claim_amount=None, vehicle_description="car",
        region="", coverage_limit=None, image_urls_for_external_search=[],
        run_external_search=False,
    )
    assert any(f.rule_id == "C-M3" for f in sub.findings)


@pytest.mark.asyncio
async def test_c_m2_price_inflation_single_part():
    sub = await _engine().analyze(
        transcript=None,
        written_description="Someone dented my front bumper in a parking lot",
        photo_zone=None, incident_dt=None, location=None,
        media_datetime_originals=[], claim_amount=1700.0,  # ~4.5x mock median 380
        vehicle_description="car", region="", coverage_limit=None,
        image_urls_for_external_search=[], run_external_search=False,
    )
    cm2 = [f for f in sub.findings if f.rule_id == "C-M2"]
    assert cm2 and cm2[0].points == 30  # ratio >= 4


@pytest.mark.asyncio
async def test_payout_cap_informational():
    sub = await _engine().analyze(
        transcript=None,
        written_description="Someone dented my front bumper in a parking lot",
        photo_zone=None, incident_dt=None, location=None,
        media_datetime_originals=[], claim_amount=1700.0,
        vehicle_description="car", region="", coverage_limit=5000.0,
        image_urls_for_external_search=[], run_external_search=False,
    )
    cap = sub.components.get("payout_cap")
    assert cap is not None and 0 < cap <= 1700.0


@pytest.mark.asyncio
async def test_c_h3_external_match_escalation_eligible():
    class MatchingSearch(MockReverseSearchProvider):
        async def search(self, image_url):
            return [{"url": "https://example-marketplace.test/car-photo", "title": "used car",
                     "source": "marketplace"}]

    engine = ConsistencyEngine(CFG, MockWeatherProvider(), MatchingSearch(),
                               MockPartPricingProvider())
    sub = await engine.analyze(
        transcript=None, written_description="rear bumper damage",
        photo_zone=None, incident_dt=None, location=None,
        media_datetime_originals=[], claim_amount=None, vehicle_description="car",
        region="", coverage_limit=None,
        image_urls_for_external_search=["https://public.test/img.jpg"],
        run_external_search=True,
    )
    ch3 = [f for f in sub.findings if f.rule_id == "C-H3"]
    assert ch3 and ch3[0].escalation_eligible is True and ch3[0].points == 50
