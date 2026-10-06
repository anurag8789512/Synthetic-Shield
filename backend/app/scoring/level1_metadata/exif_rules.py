"""EXIF/media rule functions — one pure function per anomaly check (spec §3.2).

Each takes extracted metadata + context and returns Finding | None.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta

from app.scoring.config import MetadataConfig
from app.scoring.models import Finding
from app.scoring.provenance import read_c2pa

KNOWN_EDITORS = ["photoshop", "gimp", "lightroom", "snapseed", "canva", "pixelmator", "affinity"]

# Common device screen resolutions (w, h) for screenshot detection
KNOWN_SCREEN_RESOLUTIONS = {
    (1170, 2532), (1179, 2556), (1284, 2778), (1290, 2796), (1125, 2436),
    (1080, 2340), (1080, 2400), (1440, 3200), (1080, 1920), (720, 1280),
    (828, 1792), (750, 1334), (1242, 2688), (1440, 2560), (1536, 2048),
    (2048, 2732), (1668, 2388), (1920, 1080), (2560, 1440), (3840, 2160),
    (1366, 768), (1280, 720), (2532, 1170), (2340, 1080), (2400, 1080),
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_exif_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


# EXIF DateTimeOriginal is camera-local time with no zone. Without an offset we
# can't convert to UTC, so comparisons against UTC allow the widest real offset.
MAX_TZ_OFFSET = timedelta(hours=14)
SAME_ZONE_SLACK = timedelta(minutes=5)


def capture_dt_utc(meta: dict) -> tuple[datetime | None, timedelta]:
    """(capture time as naive UTC where knowable, comparison slack)."""
    dt = parse_exif_dt(meta.get("datetime_original"))
    if not dt:
        return None, SAME_ZONE_SLACK
    if meta.get("datetime_is_utc"):
        return dt, SAME_ZONE_SLACK
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", str(meta.get("offset_time_original") or "").strip())
    if m:
        offset = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
        return (dt - offset if m.group(1) == "+" else dt + offset), SAME_ZONE_SLACK
    return dt, MAX_TZ_OFFSET


def rule_m_h1_editor_trace(meta: dict, cfg: MetadataConfig, file_id: str) -> Finding | None:
    """M-H1: editing-software trace on purportedly original capture."""
    software = " ".join(str(meta.get(k, "")) for k in ("software", "creator_tool")).lower()
    hit = next((e for e in KNOWN_EDITORS if e in software), None)
    has_xmp_history = bool(meta.get("xmp_history_edits"))
    if hit or has_xmp_history:
        label = hit.title() if hit else "XMP edit history"
        return Finding(
            rule_id="M-H1", severity="high", points=cfg.high, file_id=file_id,
            human_readable=f"File {file_id} carries a {label} editing trace but was submitted as an original capture.",
            extra={"software": software.strip()},
        )
    return None


def rule_m_h2_gps_contradiction(meta: dict, cfg: MetadataConfig, file_id: str,
                                claimed_latlon: tuple[float, float] | None) -> Finding | None:
    """M-H2: EXIF GPS present and > gps_radius_km from claimed incident location."""
    gps = meta.get("gps")
    if not gps or not claimed_latlon:
        return None
    dist = _haversine_km(gps[0], gps[1], claimed_latlon[0], claimed_latlon[1])
    if dist > cfg.gps_radius_km:
        return Finding(
            rule_id="M-H2", severity="high", points=cfg.high, file_id=file_id,
            human_readable=(
                f"File {file_id} was captured {dist:.0f} km from the claimed incident location "
                f"(threshold {cfg.gps_radius_km:.0f} km)."
            ),
            extra={"distance_km": round(dist, 1)},
        )
    return None


def rule_m_h3_impossible_timestamp(meta: dict, cfg: MetadataConfig, file_id: str,
                                   submission_dt: datetime | None,
                                   policy_start: datetime | None) -> Finding | None:
    """M-H3: DateTimeOriginal in the future / after submission / before policy start."""
    dt_orig, slack = capture_dt_utc(meta)
    if not dt_orig:
        return None
    now = datetime.utcnow()
    reasons = []
    if dt_orig > now + slack:
        reasons.append("is in the future")
    if submission_dt and dt_orig > submission_dt + slack:
        reasons.append("post-dates the claim submission")
    if policy_start and dt_orig < policy_start - MAX_TZ_OFFSET:
        reasons.append("pre-dates the policy start")
    if reasons:
        return Finding(
            rule_id="M-H3", severity="high", points=cfg.high, file_id=file_id,
            human_readable=f"Capture timestamp of {file_id} {' and '.join(reasons)}.",
            extra={"datetime_original": str(dt_orig)},
        )
    return None


def rule_m_h4_duplicate_evidence(cfg: MetadataConfig, file_id: str,
                                 matches: list) -> Finding | None:
    """M-H4: SHA-256 or pHash match against a file from a different prior claim."""
    if not matches:
        return None
    other_claims = sorted({m.claim_id for m in matches})
    return Finding(
        rule_id="M-H4", severity="high", points=cfg.high, file_id=file_id,
        human_readable=(
            f"File {file_id} matches evidence previously submitted in claim(s) "
            f"{', '.join(other_claims)}."
        ),
        extra={"matched_claims": other_claims},
    )


def rule_m_h5_screenshot(meta: dict, cfg: MetadataConfig, file_id: str) -> Finding | None:
    """M-H5: dimensions match a device screen, no camera make/model, screenshot hints."""
    dims = meta.get("dimensions")
    if not dims or tuple(dims) not in KNOWN_SCREEN_RESOLUTIONS:
        return None
    if meta.get("make") or meta.get("model"):
        return None
    name_hint = bool(re.search(r"screenshot|screen[_ -]?shot", file_id, re.I))
    png_no_exif = meta.get("format") == "PNG" and not meta.get("has_exif")
    if name_hint or png_no_exif:
        return Finding(
            rule_id="M-H5", severity="high", points=cfg.high, file_id=file_id,
            human_readable=(
                f"File {file_id} has the exact dimensions of a device screen with no camera "
                f"metadata, consistent with a screenshot rather than an original photo."
            ),
            extra={"dimensions": list(dims)},
        )
    return None


def rule_m_m1_modify_gap(meta: dict, cfg: MetadataConfig, file_id: str) -> Finding | None:
    """M-M1: DateTimeOriginal vs ModifyDate gap > threshold AND editor tag present."""
    dt_orig = parse_exif_dt(meta.get("datetime_original"))
    dt_mod = parse_exif_dt(meta.get("modify_date"))
    if not dt_orig or not dt_mod:
        return None
    software = str(meta.get("software", "")).lower()
    if not software:
        return None
    gap_h = abs((dt_mod - dt_orig).total_seconds()) / 3600.0
    if gap_h > cfg.modify_gap_hours:
        return Finding(
            rule_id="M-M1", severity="medium", points=cfg.medium, file_id=file_id,
            human_readable=(
                f"File {file_id} was modified {gap_h:.1f} hours after capture and carries a "
                f"software tag ({meta.get('software')})."
            ),
            extra={"gap_hours": round(gap_h, 1)},
        )
    return None


def rule_m_m2_timezone_inconsistency(meta: dict, cfg: MetadataConfig, file_id: str) -> Finding | None:
    """M-M2: GPS longitude implies a timezone inconsistent with EXIF local time by > 2h.

    Requires both GPS and a UTC reference (GPSTimeStamp) to compare deterministically.
    """
    gps = meta.get("gps")
    dt_orig = parse_exif_dt(meta.get("datetime_original"))
    gps_utc = meta.get("gps_utc_dt")  # datetime, from GPSDateStamp+GPSTimeStamp
    if not gps or not dt_orig or not gps_utc:
        return None
    implied_offset_h = gps[1] / 15.0  # solar-time approximation of timezone from longitude
    actual_offset_h = (dt_orig - gps_utc).total_seconds() / 3600.0
    if abs(actual_offset_h - implied_offset_h) > 2.0:
        return Finding(
            rule_id="M-M2", severity="medium", points=cfg.medium, file_id=file_id,
            human_readable=(
                f"File {file_id} local timestamp implies a UTC offset of {actual_offset_h:+.1f}h "
                f"but its GPS longitude implies roughly {implied_offset_h:+.1f}h."
            ),
            extra={"actual_offset_h": round(actual_offset_h, 1), "implied_offset_h": round(implied_offset_h, 1)},
        )
    return None


def rule_m_m4_missing_camera_fields(meta: dict, cfg: MetadataConfig, file_id: str,
                                    captured_in_app: bool) -> Finding | None:
    """M-M4: camera Make/Model absent on a file labelled as captured in-app."""
    if not captured_in_app:
        return None
    if meta.get("make") or meta.get("model"):
        return None
    return Finding(
        rule_id="M-M4", severity="medium", points=cfg.medium, file_id=file_id,
        human_readable=(
            f"File {file_id} was captured through the in-app flow but carries no camera "
            f"make/model metadata where EXIF should exist."
        ),
    )


def rule_m_l1_missing_exif(meta: dict, cfg: MetadataConfig, file_id: str,
                           captured_in_app: bool) -> Finding | None:
    """M-L1: missing EXIF on an uploaded photo. Deliberately weak — messaging apps
    strip EXIF benignly. NEVER raise this tier."""
    if captured_in_app:
        return None
    if meta.get("has_exif"):
        return None
    return Finding(
        rule_id="M-L1", severity="low", points=cfg.low, file_id=file_id,
        human_readable=(
            f"Photo {file_id} has no EXIF metadata; common for media shared via messaging "
            f"apps, so this alone is a weak signal."
        ),
    )


def rule_m_c2_intact_exif(meta: dict, cfg: MetadataConfig, file_id: str,
                          claimed_latlon: tuple[float, float] | None,
                          submission_dt: datetime | None) -> Finding | None:
    """M-C2 credit: intact camera EXIF all consistent with claim time/place."""
    dt_orig, slack = capture_dt_utc(meta)
    gps = meta.get("gps")
    if not (meta.get("make") and meta.get("model") and dt_orig and gps):
        return None
    if submission_dt and dt_orig > submission_dt + slack:
        return None
    if claimed_latlon:
        dist = _haversine_km(gps[0], gps[1], claimed_latlon[0], claimed_latlon[1])
        if dist > cfg.gps_radius_km:
            return None
    return Finding(
        rule_id="M-C2", severity="credit", points=cfg.credits.intact_exif, file_id=file_id,
        human_readable=(
            f"Photo {file_id} carries intact camera EXIF (make, model, timestamp, GPS) "
            f"consistent with the claim."
        ),
    )


def rule_m_c1_c2pa(file_path: str, cfg: MetadataConfig, file_id: str) -> Finding | None:
    """C2PA content credentials:
    M-H6 (high): the manifest declares AI generation (IPTC trainedAlgorithmicMedia);
    M-C1 (credit): a fully valid manifest from a trusted signer, not AI-declared.
    Untrusted or invalid manifests earn nothing, since anyone can self-sign one."""
    info = read_c2pa(file_path)
    if info is None:
        return None
    if info.ai_generated:
        return Finding(
            rule_id="M-H6", severity="high", points=cfg.high, file_id=file_id,
            human_readable=(f"File {file_id} carries C2PA content credentials declaring it AI-generated"
                            + (f" ({info.generator})." if info.generator else ".")),
            extra={"generator": info.generator},
        )
    if info.valid:
        return Finding(
            rule_id="M-C1", severity="credit", points=cfg.credits.c2pa, file_id=file_id,
            human_readable=f"File {file_id} carries a valid, trusted C2PA provenance manifest.",
            extra={"generator": info.generator},
        )
    return None
