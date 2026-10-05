"""
General-purpose PDF generators for reports, case files, and forensic audit exports.
"""
import io
import json
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

BRAND_BLUE = colors.HexColor("#0284C7")
BRAND_DARK = colors.HexColor("#0F172A")
BRAND_MUTED = colors.HexColor("#64748B")
BRAND_LIGHT = colors.HexColor("#F8FAFC")
BRAND_BORDER = colors.HexColor("#E2E8F0")
RED = colors.HexColor("#DC2626")
GREEN = colors.HexColor("#10B981")
AMBER = colors.HexColor("#F59E0B")


def _base_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BrandTitle", parent=styles["Title"], fontSize=18, textColor=BRAND_DARK, spaceAfter=2*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("BrandSub", parent=styles["Normal"], fontSize=9, textColor=BRAND_MUTED, spaceAfter=4*mm))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=12, textColor=BRAND_BLUE, spaceBefore=6*mm, spaceAfter=3*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, textColor=BRAND_DARK, leading=14))
    styles.add(ParagraphStyle("SmallGray", parent=styles["Normal"], fontSize=8, textColor=BRAND_MUTED))
    styles.add(ParagraphStyle("Footer", parent=styles["Normal"], alignment=TA_CENTER, fontSize=7, textColor=BRAND_MUTED))
    return styles


def _header(elements, styles, title, subtitle):
    elements.append(Paragraph("⬡ SyntheticShield", styles["BrandTitle"]))
    elements.append(Paragraph(subtitle, styles["BrandSub"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE, spaceAfter=4*mm))


def _footer(elements, styles):
    now = datetime.now(timezone.utc)
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER, spaceAfter=3*mm))
    elements.append(Paragraph(
        f"© {now.year} SyntheticShield · Confidential · Generated {now.strftime('%d %B %Y, %H:%M UTC')}",
        styles["Footer"]
    ))


def _signature_block(elements, styles, officer_name="Krishna Anurag"):
    now = datetime.now(timezone.utc)
    elements.append(Spacer(1, 8*mm))
    elements.append(HRFlowable(width="40%", thickness=0.5, color=BRAND_DARK, spaceAfter=2*mm))
    sig_data = [
        [officer_name, "", now.strftime("%d %B %Y, %H:%M UTC")],
        ["Claims Officer Lead · SyntheticShield", "", "Digital Signature"],
    ]
    sig = Table(sig_data, colWidths=[200, 100, 170])
    sig.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 1), (0, 1), BRAND_BLUE),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("ALIGNMENT", (2, 0), (2, -1), "RIGHT"),
    ]))
    elements.append(sig)


# ── Monthly/Pattern/Summary Report PDFs ──────────────────────────────────────

REPORT_CONTENT = {
    "Fraud Pattern Analysis": {
        "sections": [
            ("Executive Summary", "This report analyzes emerging fraud patterns detected by SyntheticShield's AI platform during the reporting period. Key trends include increased sophistication of AI-generated damage imagery and voice-cloned audio statements."),
            ("Detection Trends", "• Video deepfake detection rate: 94.2% accuracy\n• Voice clone detection rate: 96.1% accuracy\n• Image manipulation detection: 91.8% accuracy\n• AI-generated text detection: 99.2% accuracy"),
            ("Key Findings", "1. 68% of flagged claims used Stable Diffusion v2.1 or DALL-E 3 generated imagery\n2. Voice cloning attacks have increased 340% quarter-over-quarter\n3. Multi-modal fraud (combining fake video + fake audio) accounts for 23% of SIU cases\n4. Average fraud confidence score for confirmed cases: 91.4%"),
            ("Recommendations", "• Increase video analysis weight from 35% to 40% due to rising deepfake quality\n• Implement cross-claim narrative similarity checks (Chroma integration)\n• Expand SIU quorum from 4 to 5 officers for high-confidence cases\n• Quarterly retraining of detection models recommended"),
        ],
    },
    "Investigation Summary": {
        "sections": [
            ("Overview", "Weekly summary of SIU investigation outcomes and officer activity across all active cases during the reporting period."),
            ("Case Statistics", "• Total cases reviewed: 18\n• Confirmed fraud: 12 (66.7%)\n• Cleared: 4 (22.2%)\n• Pending: 2 (11.1%)\n• Average resolution time: 3.2 business days"),
            ("Officer Activity", "• Sarayu Vishlawath: 6 cases reviewed, 5 fraud confirmed\n• Abhishek Konnur: 5 cases reviewed, 3 fraud confirmed\n• Felina Menezes: 4 cases reviewed, 2 fraud confirmed\n• Arjun Premanathan: 3 cases reviewed, 2 fraud confirmed"),
            ("Notable Cases", "CLM-2026-00042: Highest confidence synthetic score (94%) — confirmed as AI-generated bumper damage paired with cloned voice statement. Referred to local authorities.\n\nCLM-2026-00028: Complex multi-modal fraud involving doctored dashcam footage and synthetic police report. Full investigation report attached."),
        ],
    },
    "Monthly Digest": {
        "sections": [
            ("Monthly Overview", "Comprehensive digest of claims processing, fraud detection, and platform performance for the reporting month."),
            ("Claims Processing", "• Total claims processed: 247\n• Auto-approved: 162 (65.6%)\n• Sent to moderator review: 67 (27.1%)\n• Flagged for SIU: 18 (7.3%)\n• Average processing time: 3.2 seconds per claim"),
            ("Financial Impact", "• Total fraud prevented: $124,500\n• Legitimate claims paid: $892,300\n• False positive rate: 0.8%\n• Cost savings vs. manual review: $45,200"),
            ("Platform Performance", "• Uptime: 99.97%\n• Average API response time: 142ms\n• Detection accuracy: 99.2%\n• Officer satisfaction score: 4.7/5.0"),
            ("Next Month Priorities", "• Deploy v3.3 detection model update\n• Onboard 2 additional SIU officers\n• Begin Chroma similarity integration pilot\n• Review and update adjudication thresholds"),
        ],
    },
}


def generate_report_pdf(report_id: str, title: str, report_type: str, date: str, pages: int, status: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = _base_styles()
    elements = []

    _header(elements, styles, title, f"{report_type} · {date}")

    # Meta
    meta = [
        ["Report ID:", report_id, "Type:", report_type],
        ["Date:", date, "Status:", status],
        ["Pages:", str(pages), "Classification:", "CONFIDENTIAL"],
    ]
    mt = Table(meta, colWidths=[70, 160, 80, 160])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 0), (1, -1), BRAND_DARK),
        ("TEXTCOLOR", (3, 0), (3, -1), BRAND_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 6*mm))

    # Content
    content = REPORT_CONTENT.get(report_type, REPORT_CONTENT["Monthly Digest"])
    for i, (heading, body) in enumerate(content["sections"]):
        elements.append(Paragraph(f"{i + 1}. {heading}", styles["SectionHead"]))
        for line in body.split("\n"):
            elements.append(Paragraph(line, styles["Body"]))
            elements.append(Spacer(1, 1*mm))
        elements.append(Spacer(1, 3*mm))

    _signature_block(elements, styles)
    _footer(elements, styles)

    doc.build(elements)
    return buf.getvalue()


# ── Case File Export ─────────────────────────────────────────────────────────

def generate_case_file_pdf(case: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = _base_styles()
    elements = []

    _header(elements, styles, f"Case File: {case['id']}", "SIU Investigation Case Export")

    meta = [
        ["Case ID:", case.get("id", ""), "Claim ID:", case.get("claimId", "")],
        ["Claimant:", case.get("claimant", ""), "Investigator:", case.get("investigator", "")],
        ["Status:", case.get("status", "").upper(), "Opened:", case.get("opened", "")],
        ["Risk Score:", f"{case.get('score', 0)}%", "", ""],
    ]
    mt = Table(meta, colWidths=[80, 160, 80, 150])
    mt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 0), (1, -1), BRAND_DARK),
        ("TEXTCOLOR", (3, 0), (3, -1), BRAND_DARK),
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 6*mm))

    elements.append(Paragraph("Investigator Notes", styles["SectionHead"]))
    elements.append(Paragraph(case.get("notes", "No notes available."), styles["Body"]))
    elements.append(Spacer(1, 4*mm))

    score = case.get("score", 0)
    elements.append(Paragraph("Risk Assessment", styles["SectionHead"]))
    risk_level = "LOW" if score < 30 else "MEDIUM" if score <= 70 else "HIGH"
    elements.append(Paragraph(f"Fraud Confidence Score: <b>{score}%</b> — Risk Level: <b>{risk_level}</b>", styles["Body"]))
    elements.append(Spacer(1, 2*mm))

    if score > 85:
        elements.append(Paragraph("This case exhibits strong indicators of synthetic media fraud. The AI detection system flagged multiple modalities with high-confidence synthetic signatures. SIU investigation and quorum vote are required before final disposition.", styles["Body"]))
    elif score > 50:
        elements.append(Paragraph("This case shows moderate indicators that warrant human review. Some anomalies were detected but are not conclusive enough for automatic rejection.", styles["Body"]))
    else:
        elements.append(Paragraph("This case shows minimal fraud indicators. Evidence appears largely authentic based on AI analysis.", styles["Body"]))

    _signature_block(elements, styles)
    _footer(elements, styles)

    doc.build(elements)
    return buf.getvalue()


# ── Forensic Audit Report (per claim) ────────────────────────────────────────

def generate_forensic_audit_pdf(claim_data: dict, policy_data: dict, user_data: dict, analyses: list, audit_trail: list, score_breakdown: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = _base_styles()
    elements = []

    claim_number = claim_data.get("claim_number", "N/A")
    _header(elements, styles, f"Forensic Audit Report", f"Claim {claim_number} · Complete Evidence Analysis")

    # Claim + Policy info
    elements.append(Paragraph("1. Claim & Policy Information", styles["SectionHead"]))
    info = [
        ["Claim Number:", claim_number, "Policy Number:", policy_data.get("policy_number", "N/A")],
        ["Claimant:", user_data.get("full_name", "N/A"), "Coverage:", policy_data.get("coverage_label", "Motor")],
        ["Location:", claim_data.get("accident_location", "N/A"), "Date Filed:", (claim_data.get("created_at") or "")[:10]],
        ["Status:", claim_data.get("status", "N/A").replace("_", " ").title(), "Fraud Score:", f"{claim_data.get('fraud_confidence_score', 0):.1f}%"],
    ]
    it = Table(info, colWidths=[85, 160, 80, 145])
    it.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED), ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"), ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(it)
    elements.append(Spacer(1, 2*mm))

    elements.append(Paragraph(f"<b>Incident:</b> {claim_data.get('accident_description', 'N/A')}", styles["Body"]))
    elements.append(Spacer(1, 4*mm))

    # Fusion score breakdown by analysis level
    section_no = 2
    if score_breakdown:
        elements.append(Paragraph(f"{section_no}. Fraud Score Division by Analysis Level", styles["SectionHead"]))
        section_no += 1

        LEVEL_OF = {"metadata": "Level 1 · Metadata Analysis",
                    "image": "Level 2 · AI Manipulation", "video": "Level 2 · AI Manipulation",
                    "audio": "Level 2 · AI Manipulation", "text": "Level 2 · AI Manipulation",
                    "consistency": "Level 3 · Consistency Check"}
        weights = score_breakdown.get("weights_used", {})
        rows = [["Level", "Signal", "Score", "Weight", "Status"]]
        for sub in score_breakdown.get("subscores", []):
            name = sub.get("name", "")
            value = sub.get("value")
            w = weights.get(name)
            rows.append([
                LEVEL_OF.get(name, "Level 2 · AI Manipulation"),
                name.capitalize(),
                f"{value:.1f} / 100" if value is not None else "—",
                f"{w:.0%}" if w is not None else "—",
                sub.get("status", "ok").replace("_", " "),
            ])
        bt = Table(rows, colWidths=[140, 80, 75, 60, 115])
        bt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_MUTED),
            ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(bt)
        elements.append(Spacer(1, 2*mm))

        fusion_line = (f"<b>Base score:</b> {score_breakdown.get('base_score', 0):.1f} · "
                       f"<b>Final score:</b> {score_breakdown.get('final_score', 0):.1f} · "
                       f"<b>Routing:</b> {str(score_breakdown.get('routing_band', '')).replace('_', ' ').title()}")
        if score_breakdown.get("escalated"):
            fusion_line += f" · <b>Worst-signal escalation:</b> fired via {score_breakdown.get('escalation_source')}"
        if score_breakdown.get("forced_review_reason"):
            fusion_line += f" · <b>Forced review:</b> {score_breakdown.get('forced_review_reason')}"
        elements.append(Paragraph(fusion_line, styles["Body"]))
        elements.append(Paragraph(
            f"Scoring engine config {score_breakdown.get('config_version', 'n/a')} · "
            f"score version {score_breakdown.get('version', 1)} · weights re-normalized over available signals.",
            styles["SmallGray"]))
        elements.append(Spacer(1, 4*mm))

    # Per-modality analysis
    elements.append(Paragraph(f"{section_no}. Multi-Modal Detection Analysis", styles["SectionHead"]))
    section_no += 1
    for a in analyses:
        modality = a.get("modality", "unknown").capitalize()
        score = a.get("raw_score")
        provider = a.get("provider", "mock").replace("_", " ").title()
        if score is None:
            # signal was unavailable/not applicable (e.g. vendor outage, no media)
            elements.append(Paragraph(f"<b>{modality}</b> — Score: unavailable — Provider: {provider}", styles["Body"]))
        else:
            sev_label = "LOW" if score < 30 else "MEDIUM" if score <= 70 else "HIGH"
            elements.append(Paragraph(f"<b>{modality}</b> — Score: {score:.1f}% ({sev_label}) — Provider: {provider}", styles["Body"]))

        findings_data = a.get("findings_json", "{}")
        if isinstance(findings_data, str):
            try:
                findings_data = json.loads(findings_data)
            except:
                findings_data = {}
        for f in findings_data.get("findings", []):
            detail = f.get("detail", "") if isinstance(f, dict) else str(f)
            ts = f.get("timestamp_or_location", "") if isinstance(f, dict) else ""
            line = f"  • {detail}"
            if ts:
                line += f" [{ts}]"
            elements.append(Paragraph(line, styles["SmallGray"]))
        elements.append(Spacer(1, 3*mm))

    # Audit trail
    if audit_trail:
        elements.append(Paragraph(f"{section_no}. Audit Trail", styles["SectionHead"]))
        trail_data = [["Time", "Actor", "Action", "Details"]]
        for t in audit_trail:
            ts = (t.get("created_at") or t.get("timestamp") or "")
            if ts:
                try:
                    ts = datetime.fromisoformat(ts).strftime("%H:%M:%S")
                except:
                    ts = ts[:8]
            details = ""
            dj = t.get("details_json", "")
            if dj:
                try:
                    d = json.loads(dj) if isinstance(dj, str) else dj
                    details = ", ".join(f"{k}={v}" for k, v in d.items())[:60]
                except:
                    pass
            trail_data.append([ts, t.get("actor_type", ""), t.get("action", ""), details])

        tt = Table(trail_data, colWidths=[55, 55, 130, 230])
        tt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_MUTED),
            ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(tt)

    _signature_block(elements, styles)
    _footer(elements, styles)

    doc.build(elements)
    return buf.getvalue()
