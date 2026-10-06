"""Level 1 — MetadataAnalyzer: extracts metadata from every uploaded file and
runs the §3.2 rule battery. S_metadata = clamp(sum(points), 0, 100).
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from app.scoring.config import ScoringConfig
from app.scoring.level1_metadata import exif_rules, pdf_rules
from app.scoring.models import Finding, SubScore
from app.scoring import persistence

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm", ".opus", ".flac"}

_COORD_RE = re.compile(r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")


def parse_latlon(location: str | None) -> tuple[float, float] | None:
    """Parse 'lat, lon' coordinates out of a free-text location string, if present."""
    if not location:
        return None
    m = _COORD_RE.search(location)
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return (lat, lon)
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_phash(path: Path) -> str | None:
    try:
        import imagehash
        from PIL import Image
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def _ratio_to_float(v) -> float:
    try:
        return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
    except (TypeError, ZeroDivisionError, ValueError):
        return 0.0


def extract_image_meta(path: Path) -> dict:
    """EXIF extraction via piexif + Pillow. Returns normalized metadata dict."""
    meta: dict = {"has_exif": False, "format": None, "dimensions": None}
    try:
        from PIL import Image
        with Image.open(path) as img:
            meta["format"] = img.format
            meta["dimensions"] = (img.width, img.height)
            exif_bytes = img.info.get("exif")
            xmp = img.info.get("XML:com.adobe.xmp") or img.info.get("xmp") or b""
            if xmp:
                xmp_text = xmp.decode("utf-8", "ignore") if isinstance(xmp, bytes) else str(xmp)
                if "xmpMM:History" in xmp_text:
                    meta["xmp_history_edits"] = True
                m = re.search(r'CreatorTool[=">]+([^"<]+)', xmp_text)
                if m:
                    meta["creator_tool"] = m.group(1)
    except Exception:
        return meta

    if not exif_bytes:
        return meta
    try:
        import piexif
        exif = piexif.load(exif_bytes)
    except Exception:
        return meta

    meta["has_exif"] = True
    zeroth, exif_ifd, gps_ifd = exif.get("0th", {}), exif.get("Exif", {}), exif.get("GPS", {})

    def _s(v):
        return v.decode("utf-8", "ignore").strip("\x00 ") if isinstance(v, bytes) else v

    import piexif as _p
    meta["make"] = _s(zeroth.get(_p.ImageIFD.Make)) or None
    meta["model"] = _s(zeroth.get(_p.ImageIFD.Model)) or None
    meta["software"] = _s(zeroth.get(_p.ImageIFD.Software)) or None
    meta["modify_date"] = _s(zeroth.get(_p.ImageIFD.DateTime)) or None
    meta["datetime_original"] = _s(exif_ifd.get(_p.ExifIFD.DateTimeOriginal)) or None
    # EXIF 2.31 OffsetTimeOriginal (tag 36881), e.g. "+05:30" — lets us convert to UTC
    meta["offset_time_original"] = _s(exif_ifd.get(36881)) or None

    if gps_ifd.get(_p.GPSIFD.GPSLatitude) and gps_ifd.get(_p.GPSIFD.GPSLongitude):
        def _dms(dms, ref):
            deg = _ratio_to_float(dms[0]) + _ratio_to_float(dms[1]) / 60 + _ratio_to_float(dms[2]) / 3600
            ref_s = _s(ref) or ""
            return -deg if ref_s in ("S", "W") else deg
        try:
            lat = _dms(gps_ifd[_p.GPSIFD.GPSLatitude], gps_ifd.get(_p.GPSIFD.GPSLatitudeRef))
            lon = _dms(gps_ifd[_p.GPSIFD.GPSLongitude], gps_ifd.get(_p.GPSIFD.GPSLongitudeRef))
            meta["gps"] = (lat, lon)
        except (KeyError, IndexError, TypeError):
            pass
        # GPS UTC reference for the timezone rule
        gps_date = _s(gps_ifd.get(_p.GPSIFD.GPSDateStamp))
        gps_time = gps_ifd.get(_p.GPSIFD.GPSTimeStamp)
        if gps_date and gps_time:
            try:
                h, mnt, s = (_ratio_to_float(x) for x in gps_time)
                meta["gps_utc_dt"] = datetime.strptime(gps_date, "%Y:%m:%d").replace(
                    hour=int(h), minute=int(mnt), second=int(s))
            except (ValueError, TypeError):
                pass
    return meta


def extract_container_meta(path: Path) -> dict:
    """Video/audio container metadata via ffprobe (subprocess)."""
    import json as _json
    import subprocess
    meta: dict = {"has_exif": False}
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, timeout=30,
        )
        data = _json.loads(out.stdout or b"{}")
        tags = (data.get("format") or {}).get("tags") or {}
        meta["software"] = tags.get("encoder") or tags.get("com.apple.quicktime.software")
        meta["datetime_original"] = (tags.get("creation_time") or "").replace("T", " ").split(".")[0] or None
        meta["datetime_is_utc"] = True  # container creation_time is ISO-8601 UTC
        meta["make"] = tags.get("com.apple.quicktime.make")
        meta["model"] = tags.get("com.apple.quicktime.model")
        loc = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709")
        if loc:
            m = re.match(r"([+-]\d+\.\d+)([+-]\d+\.\d+)", loc)
            if m:
                meta["gps"] = (float(m.group(1)), float(m.group(2)))
        meta["has_exif"] = bool(meta.get("datetime_original") or meta.get("make"))
    except Exception:
        pass
    return meta


class MetadataAnalyzer:
    """Runs all Level 1 rules across every uploaded file for a claim."""

    def __init__(self, config: ScoringConfig):
        self.config = config

    def analyze(self, db: DBSession, claim_id: str, files: list[dict],
                claimed_location: str | None,
                submission_dt: datetime | None,
                policy_start: datetime | None) -> SubScore:
        """files: [{"path": Path, "media_type": "image"|"video"|"audio"|"pdf",
                    "captured_in_app": bool, "claimed_official": bool}]
        """
        cfg = self.config.metadata
        claimed_latlon = parse_latlon(claimed_location)
        findings: list[Finding] = []
        analyzed_any = False

        for f in files:
            path: Path = Path(f["path"])
            if not path.exists():
                continue
            analyzed_any = True
            file_id = path.name
            media_type = f["media_type"]
            captured_in_app = bool(f.get("captured_in_app"))

            if media_type == "pdf":
                pmeta = pdf_rules.extract_pdf_meta(str(path))
                for rule_result in (
                    pdf_rules.rule_m_m3_pdf_resaved(pmeta, cfg, file_id),
                    pdf_rules.rule_m_l2_generic_producer(pmeta, cfg, file_id,
                                                         bool(f.get("claimed_official"))),
                ):
                    if rule_result:
                        findings.append(rule_result)
                continue

            meta = extract_image_meta(path) if media_type == "image" else extract_container_meta(path)

            # duplicate-evidence check against internal hash DB (M-H4)
            sha = _sha256(path)
            phash = compute_phash(path) if media_type == "image" else None
            matches = persistence.find_hash_matches(db, claim_id, sha, phash, cfg.phash_threshold)
            persistence.record_evidence_hash(db, claim_id, file_id, sha, phash, media_type)

            checks = [
                exif_rules.rule_m_h1_editor_trace(meta, cfg, file_id),
                exif_rules.rule_m_h2_gps_contradiction(meta, cfg, file_id, claimed_latlon),
                exif_rules.rule_m_h3_impossible_timestamp(meta, cfg, file_id, submission_dt, policy_start),
                exif_rules.rule_m_h4_duplicate_evidence(cfg, file_id, matches),
                exif_rules.rule_m_m1_modify_gap(meta, cfg, file_id),
                exif_rules.rule_m_m2_timezone_inconsistency(meta, cfg, file_id),
                exif_rules.rule_m_m4_missing_camera_fields(meta, cfg, file_id,
                                                           captured_in_app and media_type in ("image", "video")),
                exif_rules.rule_m_c1_c2pa(str(path), cfg, file_id),
                exif_rules.rule_m_c2_intact_exif(meta, cfg, file_id, claimed_latlon, submission_dt),
            ]
            if media_type == "image":
                checks.append(exif_rules.rule_m_h5_screenshot(meta, cfg, file_id))
                checks.append(exif_rules.rule_m_l1_missing_exif(meta, cfg, file_id, captured_in_app))
            findings.extend(c for c in checks if c)

        if not analyzed_any:
            return SubScore(name="metadata", status="not_applicable", provider="in_house_metadata_v1")
        total = sum(f.points for f in findings)
        value = max(0.0, min(100.0, total))
        return SubScore(name="metadata", value=value, status="ok",
                        findings=findings, provider="in_house_metadata_v1")
