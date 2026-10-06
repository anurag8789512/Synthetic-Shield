"""Deterministic fact extraction: transcript + written statement → IncidentFacts.

Keyword maps are explicit dictionaries; no LLM anywhere (spec §5.1). Speech-to-text
happens upstream (app/scoring/stt.py); this module only consumes text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IncidentFacts:
    source: str                      # "voice" | "written" | "photos" | "claim_form"
    incident_type: str | None = None   # rear_end | side_impact | front_collision | parked | theft | weather | other
    impact_zone: str | None = None     # front | rear | left | right | roof | multiple
    incident_dt: datetime | None = None
    location: tuple[float, float] | None = None
    weather_claimed: str | None = None  # hail | storm | rain | flood | None
    damaged_parts: list[str] = field(default_factory=list)


INCIDENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "rear_end": ["rear-end", "rear end", "rearend", "hit from behind", "ran into the back",
                 "hit me from behind", "rammed from behind"],
    "side_impact": ["t-bone", "t bone", "side impact", "side-swipe", "sideswipe", "hit the side",
                    "broadside", "hit my side"],
    "front_collision": ["head-on", "head on", "front collision", "frontal collision",
                        "crashed into the front", "hit the front"],
    "parked": ["parked", "parking lot", "while parked", "car park"],
    "theft": ["stolen", "theft", "broke into", "break-in", "burglar"],
    "weather": ["hail", "hailstorm", "storm", "flood", "flooded", "hurricane", "tornado",
                "heavy rain", "cyclone"],
}

IMPACT_ZONE_KEYWORDS: dict[str, list[str]] = {
    "front": ["front bumper", "front of the car", "front end", "hood", "bonnet", "windshield",
              "front grill", "grille", "headlight", "front fender", "front damage", "the front"],
    "rear": ["rear bumper", "back of the car", "rear end", "trunk", "boot", "tail light",
             "taillight", "rear windshield", "rear damage", "the rear", "the back"],
    "left": ["left door", "left side", "driver side", "driver's side", "left fender",
             "left quarter", "left mirror"],
    "right": ["right door", "right side", "passenger side", "passenger's side", "right fender",
              "right quarter", "right mirror"],
    "roof": ["roof", "sunroof", "top of the car"],
}

WEATHER_KEYWORDS: dict[str, list[str]] = {
    "hail": ["hail", "hailstorm", "hailstones"],
    "storm": ["storm", "thunderstorm", "hurricane", "tornado", "cyclone", "high winds"],
    "rain": ["heavy rain", "raining", "rainstorm", "downpour"],
    "flood": ["flood", "flooded", "waterlogged", "submerged"],
}

DAMAGED_PART_KEYWORDS: dict[str, list[str]] = {
    "front_bumper": ["front bumper"],
    "rear_bumper": ["rear bumper", "back bumper"],
    "hood": ["hood", "bonnet"],
    "trunk": ["trunk", "boot lid", "tailgate"],
    "windshield": ["windshield", "windscreen", "front glass"],
    "rear_windshield": ["rear windshield", "rear glass", "back glass"],
    "headlight": ["headlight", "head lamp", "headlamp"],
    "taillight": ["tail light", "taillight", "tail lamp"],
    "left_door": ["left door", "driver door", "driver's door"],
    "right_door": ["right door", "passenger door", "passenger's door"],
    "fender": ["fender", "wing panel"],
    "side_mirror": ["side mirror", "wing mirror", "door mirror"],
    "roof": ["roof panel", "sunroof", "roof"],
    "grille": ["grill", "grille"],
    "wheel": ["wheel", "rim", "alloy"],
    "quarter_panel": ["quarter panel"],
}

# Fixed compatibility matrix for C-M3: incident_type → plausible impact zones.
INCIDENT_ZONE_COMPATIBILITY: dict[str, set[str]] = {
    "rear_end": {"rear", "multiple"},
    "front_collision": {"front", "multiple"},
    "side_impact": {"left", "right", "multiple"},
    "parked": {"front", "rear", "left", "right", "multiple"},  # scrapes: any side, not roof
    "weather": {"roof", "front", "rear", "left", "right", "multiple"},
    "theft": set(),   # no impact-zone expectation
    "other": set(),
}

# Hard pairwise conflicts for C-H1
HARD_CONFLICTS = [{"front", "rear"}, {"left", "right"}]


def _find(text: str, kw: str) -> int:
    """Position of kw as a whole word (plural/verb suffixes allowed), else -1 — so "rim"
    doesn't hit "crime" and "hood" doesn't hit "neighborhood"."""
    m = re.search(rf"(?<![a-z]){re.escape(kw)}(?:e?s|e?d|ing)?(?![a-z])", text)
    return m.start() if m else -1


def _has(text: str, kws: list[str]) -> bool:
    return any(_find(text, kw) >= 0 for kw in kws)


def _first_match(text: str, keyword_map: dict[str, list[str]]) -> str | None:
    hits = []
    for label, kws in keyword_map.items():
        for kw in kws:
            pos = _find(text, kw)
            if pos >= 0:
                hits.append((pos, len(kw), label))
                break
    if not hits:
        return None
    # earliest, then longest match wins — deterministic
    hits.sort(key=lambda h: (h[0], -h[1]))
    return hits[0][2]


def _all_zone_matches(text: str) -> list[str]:
    zones = [z for z, kws in IMPACT_ZONE_KEYWORDS.items() if _has(text, kws)]
    return zones


def extract_facts(text: str | None, source: str,
                  incident_dt: datetime | None = None,
                  location: tuple[float, float] | None = None) -> IncidentFacts:
    facts = IncidentFacts(source=source, incident_dt=incident_dt, location=location)
    if not text:
        return facts
    t = re.sub(r"\s+", " ", text.lower())

    facts.incident_type = _first_match(t, INCIDENT_TYPE_KEYWORDS)
    zones = _all_zone_matches(t)
    if len(zones) > 1:
        # true multi-zone only when no hard conflict; conflicts stay visible to C-H1
        facts.impact_zone = "multiple" if not _has_hard_conflict(zones) else zones[0]
        facts.damaged_parts = _parts(t)
        facts.weather_claimed = _first_match(t, WEATHER_KEYWORDS)
        facts._all_zones = zones  # type: ignore[attr-defined]
        return facts
    facts.impact_zone = zones[0] if zones else None
    facts.weather_claimed = _first_match(t, WEATHER_KEYWORDS)
    facts.damaged_parts = _parts(t)
    facts._all_zones = zones  # type: ignore[attr-defined]
    return facts


def _parts(t: str) -> list[str]:
    parts = []
    for part, kws in DAMAGED_PART_KEYWORDS.items():
        if _has(t, kws) and part not in parts:
            parts.append(part)
    return parts


def _has_hard_conflict(zones: list[str]) -> bool:
    zone_set = set(zones)
    return any(conflict <= zone_set for conflict in HARD_CONFLICTS)


def zones_conflict(zone_a: str | None, zone_b: str | None) -> bool:
    """Hard pairwise conflict test (front vs rear; left vs right)."""
    if not zone_a or not zone_b or "multiple" in (zone_a, zone_b):
        return False
    return {zone_a, zone_b} in HARD_CONFLICTS
