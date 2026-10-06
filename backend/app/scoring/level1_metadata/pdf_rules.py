"""PDF metadata rule functions (spec §3.2 M-M3, M-L2)."""
from __future__ import annotations

import re

from app.scoring.config import MetadataConfig
from app.scoring.models import Finding

GENERIC_PRODUCERS = [
    "microsoft: print to pdf", "microsoft print to pdf", "chrome", "chromium",
    "mozilla", "firefox", "safari", "edge", "wkhtmltopdf", "print to pdf",
]


def extract_pdf_meta(path: str) -> dict:
    """Extract Creator/Producer and count incremental revisions via pypdf + raw scan."""
    meta: dict = {"creator": None, "producer": None, "revisions": 1}
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        info = reader.metadata or {}
        meta["creator"] = str(info.get("/Creator") or "") or None
        meta["producer"] = str(info.get("/Producer") or "") or None
    except Exception:
        pass
    try:
        raw = open(path, "rb").read()
        # each %%EOF marks the end of a cross-reference revision; linearized
        # ("fast web view") PDFs are written with two sections from the start
        eofs = raw.count(b"%%EOF")
        if b"/Linearized" in raw[:2048]:
            eofs -= 1
        meta["revisions"] = max(eofs, 1)
    except OSError:
        pass
    return meta


def rule_m_m3_pdf_resaved(meta: dict, cfg: MetadataConfig, file_id: str) -> Finding | None:
    """M-M3: Creator/Producer indicate different tools OR >= 2 xref revisions."""
    creator = (meta.get("creator") or "").strip().lower()
    producer = (meta.get("producer") or "").strip().lower()
    different_tools = bool(creator and producer) and creator not in producer and producer not in creator
    multiple_revisions = meta.get("revisions", 1) >= 2
    if different_tools or multiple_revisions:
        reason = []
        if different_tools:
            reason.append(f"created with '{meta['creator']}' but produced by '{meta['producer']}'")
        if multiple_revisions:
            reason.append(f"{meta['revisions']} incremental revisions after creation")
        return Finding(
            rule_id="M-M3", severity="medium", points=cfg.medium, file_id=file_id,
            human_readable=f"Document {file_id} was re-saved: {'; '.join(reason)}.",
            extra={"creator": meta.get("creator"), "producer": meta.get("producer"),
                   "revisions": meta.get("revisions")},
        )
    return None


def rule_m_l2_generic_producer(meta: dict, cfg: MetadataConfig, file_id: str,
                               claimed_official: bool) -> Finding | None:
    """M-L2: generic print-to-PDF producer on a document claimed as official/original."""
    if not claimed_official:
        return None
    producer = (meta.get("producer") or "").strip().lower()
    if any(re.search(rf"(?<![a-z]){re.escape(g)}(?![a-z])", producer) for g in GENERIC_PRODUCERS):
        return Finding(
            rule_id="M-L2", severity="low", points=cfg.low, file_id=file_id,
            human_readable=(
                f"Document {file_id} was produced via a generic print-to-PDF tool "
                f"({meta.get('producer')}) despite being submitted as an official document."
            ),
        )
    return None
