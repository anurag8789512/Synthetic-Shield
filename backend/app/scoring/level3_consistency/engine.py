"""Level 3 — ConsistencyEngine: cross-evidence deterministic rules (spec §5).

Additive penalties, clamp [0,100]. Also computes the informational payout_cap.
"""
from __future__ import annotations

from datetime import datetime

from app.scoring.config import ScoringConfig
from app.scoring.level1_metadata.exif_rules import parse_exif_dt
from app.scoring.level3_consistency import fact_extraction as fx
from app.scoring.level3_consistency.part_pricing import PartPricingProvider, get_market_estimate
from app.scoring.level3_consistency.reverse_search import ReverseSearchProvider
from app.scoring.level3_consistency.weather import WeatherProvider
from app.scoring.models import Finding, SubScore

C_H1_POINTS = 45.0
C_H2_POINTS = 45.0
C_H3_POINTS = 50.0
C_M1_POINTS = 25.0
C_M2_POINTS_2X = 15.0
C_M2_POINTS_4X = 30.0
C_M2_CAP = 45.0
C_M3_POINTS = 25.0
C_L1_POINTS = 10.0


class ConsistencyEngine:
    def __init__(self, config: ScoringConfig,
                 weather_provider: WeatherProvider,
                 reverse_search_provider: ReverseSearchProvider,
                 pricing_provider: PartPricingProvider):
        self.config = config
        self.weather = weather_provider
        self.reverse_search = reverse_search_provider
        self.pricing = pricing_provider

    async def analyze(self, *,
                      transcript: str | None,
                      written_description: str | None,
                      photo_zone: str | None,
                      incident_dt: datetime | None,
                      location: tuple[float, float] | None,
                      media_datetime_originals: list[str],
                      claim_amount: float | None,
                      vehicle_description: str,
                      region: str,
                      coverage_limit: float | None,
                      image_urls_for_external_search: list[str],
                      run_external_search: bool) -> SubScore:
        cfg = self.config.consistency
        findings: list[Finding] = []

        voice_facts = fx.extract_facts(transcript, "voice", incident_dt, location)
        written_facts = fx.extract_facts(written_description, "written", incident_dt, location)
        photo_facts = fx.IncidentFacts(source="photos", impact_zone=photo_zone)
        incident_type = written_facts.incident_type or voice_facts.incident_type

        # C-H1: hard narrative contradiction (pairwise; one award per pair type)
        pairs = [("voice", voice_facts.impact_zone, "written", written_facts.impact_zone),
                 ("voice", voice_facts.impact_zone, "photos", photo_facts.impact_zone),
                 ("written", written_facts.impact_zone, "photos", photo_facts.impact_zone)]
        awarded_pair_types: set[frozenset] = set()
        for src_a, zone_a, src_b, zone_b in pairs:
            if fx.zones_conflict(zone_a, zone_b):
                pair_type = frozenset({zone_a, zone_b})
                if pair_type in awarded_pair_types:
                    continue
                awarded_pair_types.add(pair_type)
                findings.append(Finding(
                    rule_id="C-H1", severity="high", points=C_H1_POINTS,
                    human_readable=(f"The {src_a} statement describes {zone_a} damage but the "
                                    f"{src_b} evidence indicates {zone_b} damage — a hard contradiction."),
                    extra={"sources": [src_a, src_b], "zones": [zone_a, zone_b]},
                ))

        # C-H2: weather contradiction
        weather_claimed = written_facts.weather_claimed or voice_facts.weather_claimed
        if weather_claimed and location and incident_dt:
            had = await self.weather.had_event(location[0], location[1], incident_dt,
                                               weather_claimed, cfg.weather_window_h)
            if had is False:
                findings.append(Finding(
                    rule_id="C-H2", severity="high", points=C_H2_POINTS,
                    human_readable=(f"The claim cites {weather_claimed} damage but historical weather "
                                    f"records show no such event within ±{cfg.weather_window_h:.0f}h "
                                    f"at the incident location."),
                    extra={"weather_claimed": weather_claimed},
                ))

        # C-H3: external reverse image search (conditional per §5.3)
        if run_external_search:
            for url in image_urls_for_external_search:
                matches = await self.reverse_search.search(url)
                if matches:
                    findings.append(Finding(
                        rule_id="C-H3", severity="high", points=C_H3_POINTS,
                        escalation_eligible=True,
                        human_readable=("A claim photo was found on the public web, indicating it may "
                                        "predate the incident or belong to a third party."),
                        extra={"matched_urls": [m["url"] for m in matches[:5]]},
                    ))
                    break  # one award

        # C-M1: media captured earlier than claimed incident time
        if incident_dt:
            for dto in media_datetime_originals:
                dt = parse_exif_dt(dto)
                if dt and (incident_dt - dt).total_seconds() / 3600.0 > cfg.temporal_gap_h:
                    gap_h = (incident_dt - dt).total_seconds() / 3600.0
                    findings.append(Finding(
                        rule_id="C-M1", severity="medium", points=C_M1_POINTS,
                        human_readable=(f"Evidence was captured {gap_h:.1f} hours before the claimed "
                                        f"incident time."),
                        extra={"media_dt": str(dt), "incident_dt": str(incident_dt)},
                    ))
                    break

        # C-M2: per-part price inflation + informational payout cap
        payout_cap: float | None = None
        damaged_parts = written_facts.damaged_parts or voice_facts.damaged_parts
        estimates: dict[str, float] = {}
        for part in damaged_parts:
            est = await get_market_estimate(part, vehicle_description, region, self.pricing,
                                            self.config.pricing.cache_days,
                                            self.config.pricing.min_price_points)
            if est is not None:
                estimates[part] = est
        # Without line-item costs, a single damaged part lets us attribute the full
        # claimed amount to that part; multi-part claims skip C-M2 (never guess).
        cm2_total = 0.0
        if claim_amount and len(damaged_parts) == 1 and damaged_parts[0] in estimates:
            part = damaged_parts[0]
            ratio = claim_amount / max(estimates[part], 1e-9)
            pts = C_M2_POINTS_4X if ratio >= 4.0 else C_M2_POINTS_2X if ratio >= 2.0 else 0.0
            pts = min(pts, C_M2_CAP - cm2_total)
            if pts > 0:
                cm2_total += pts
                findings.append(Finding(
                    rule_id="C-M2", severity="medium", points=pts,
                    human_readable=(f"Claimed cost for the {part.replace('_', ' ')} is {ratio:.1f}× "
                                    f"the market median estimate."),
                    extra={"part": part, "ratio": round(ratio, 2),
                           "market_estimate": estimates[part]},
                ))
        if claim_amount is not None and estimates:
            market_sum = sum(estimates.values()) * (1 + self.config.pricing.labor_buffer)
            caps = [claim_amount, market_sum]
            if coverage_limit is not None:
                caps.append(coverage_limit)
            payout_cap = min(caps)

        # C-M3: damage-pattern implausibility (fixed compatibility matrix)
        observed_zone = photo_facts.impact_zone or written_facts.impact_zone or voice_facts.impact_zone
        if incident_type and observed_zone:
            compatible = fx.INCIDENT_ZONE_COMPATIBILITY.get(incident_type, set())
            if compatible and observed_zone not in compatible:
                findings.append(Finding(
                    rule_id="C-M3", severity="medium", points=C_M3_POINTS,
                    human_readable=(f"A {incident_type.replace('_', ' ')} incident is implausible with "
                                    f"{observed_zone} damage."),
                    extra={"incident_type": incident_type, "impact_zone": observed_zone},
                ))

        # C-L1: minor narrative discrepancy (part list differs by one minor item)
        if voice_facts.damaged_parts and written_facts.damaged_parts:
            diff = set(voice_facts.damaged_parts) ^ set(written_facts.damaged_parts)
            if len(diff) == 1 and not any(f.rule_id == "C-H1" for f in findings):
                findings.append(Finding(
                    rule_id="C-L1", severity="low", points=C_L1_POINTS,
                    human_readable=(f"The voice and written statements differ on one damaged part "
                                    f"({next(iter(diff)).replace('_', ' ')})."),
                    extra={"differing_part": next(iter(diff))},
                ))

        total = sum(f.points for f in findings)
        value = max(0.0, min(100.0, total))
        sub = SubScore(name="consistency", value=value, status="ok",
                       findings=findings, provider="in_house_consistency_v1")
        sub.components["payout_cap"] = payout_cap if payout_cap is not None else -1.0
        return sub
