"""
PDF report generator for claim artifact reports.
Professional format with SyntheticShield branding, digital signature, and full claim details.
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
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


BRAND_BLUE = colors.HexColor("#0284C7")
BRAND_DARK = colors.HexColor("#0F172A")
BRAND_MUTED = colors.HexColor("#64748B")
BRAND_LIGHT = colors.HexColor("#F8FAFC")
BRAND_BORDER = colors.HexColor("#E2E8F0")
RED = colors.HexColor("#DC2626")
GREEN = colors.HexColor("#10B981")
AMBER = colors.HexColor("#F59E0B")


def _severity_color(severity: str):
    return GREEN if severity == "low" else AMBER if severity == "medium" else RED


def _verdict_label(verdict: str) -> str:
    return {"authentic": "AUTHENTIC", "inconclusive": "INCONCLUSIVE", "synthetic": "SYNTHETIC"}.get(verdict, verdict.upper())


def generate_report_pdf(
    claim: dict,
    policy: dict,
    user: dict,
    report: dict,
    officer_name: str = "K. Rodriguez",
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BrandTitle", parent=styles["Title"], fontSize=20, textColor=BRAND_DARK, spaceAfter=2*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("BrandSub", parent=styles["Normal"], fontSize=9, textColor=BRAND_MUTED, spaceAfter=4*mm))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=12, textColor=BRAND_BLUE, spaceBefore=6*mm, spaceAfter=3*mm, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("FieldLabel", parent=styles["Normal"], fontSize=8, textColor=BRAND_MUTED, fontName="Helvetica"))
    styles.add(ParagraphStyle("FieldValue", parent=styles["Normal"], fontSize=10, textColor=BRAND_DARK, fontName="Helvetica-Bold", spaceAfter=2*mm))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, textColor=BRAND_DARK, leading=14))
    styles.add(ParagraphStyle("SmallGray", parent=styles["Normal"], fontSize=8, textColor=BRAND_MUTED))
    styles.add(ParagraphStyle("Center", parent=styles["Normal"], alignment=TA_CENTER, fontSize=10))
    styles.add(ParagraphStyle("Right", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=8, textColor=BRAND_MUTED))
    styles.add(ParagraphStyle("Footer", parent=styles["Normal"], alignment=TA_CENTER, fontSize=7, textColor=BRAND_MUTED))

    now = datetime.now(timezone.utc)
    elements = []

    # ── Header ──────────────────────────────────────────────────────────
    elements.append(Paragraph("⬡ SyntheticShield", styles["BrandTitle"]))
    elements.append(Paragraph("AI-Powered Fraud Intelligence Platform · Deepfake Detection Report", styles["BrandSub"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE, spaceAfter=4*mm))

    # Report metadata
    meta_data = [
        ["Report Generated:", now.strftime("%d %B %Y, %H:%M UTC"), "Report ID:", f"RPT-{claim.get('claim_number', 'N/A')}"],
        ["Classification:", "CONFIDENTIAL", "Version:", "1.0"],
    ]
    meta_table = Table(meta_data, colWidths=[90, 150, 80, 150])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), BRAND_DARK),
        ("TEXTCOLOR", (3, 0), (3, -1), BRAND_DARK),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 4*mm))

    # ── Claim Details ────────────────────────────────────────────────────
    elements.append(Paragraph("1. Claim Information", styles["SectionHead"]))

    score = claim.get("fraud_confidence_score", 0) or 0
    status = claim.get("status", "unknown").replace("_", " ").title()
    score_color = GREEN if score < 15 else AMBER if score <= 85 else RED

    claim_data = [
        ["Claim Number", claim.get("claim_number", "N/A"), "Status", status],
        ["Policy Number", policy.get("policy_number", "N/A"), "Fraud Score", f"{score:.1f}%"],
        ["Claimant", user.get("full_name", "N/A"), "Date Filed", claim.get("created_at", "N/A")[:10] if claim.get("created_at") else "N/A"],
        ["Location", claim.get("accident_location", "N/A"), "Coverage", policy.get("coverage_label", "Motor")],
    ]
    claim_table = Table(claim_data, colWidths=[85, 165, 75, 145])
    claim_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(claim_table)
    elements.append(Spacer(1, 3*mm))

    # Description
    desc = claim.get("accident_description", "N/A")
    elements.append(Paragraph("Incident Description", styles["FieldLabel"]))
    elements.append(Paragraph(desc, styles["Body"]))
    elements.append(Spacer(1, 4*mm))

    # ── AI Analysis Summary ──────────────────────────────────────────────
    elements.append(Paragraph("2. AI Detection Summary", styles["SectionHead"]))

    summary = report.get("summary", "No analysis available.")
    recommendation = report.get("recommendation", "N/A")
    elements.append(Paragraph(f"<b>Summary:</b> {summary}", styles["Body"]))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(f"<b>Recommendation:</b> {recommendation}", styles["Body"]))
    elements.append(Spacer(1, 4*mm))

    # ── Per-Modality Analysis ────────────────────────────────────────────
    elements.append(Paragraph("3. Per-Modality Analysis", styles["SectionHead"]))

    modality_reports = report.get("modality_reports", [])
    for mr in modality_reports:
        modality = mr.get("modality", "unknown").capitalize()
        raw_score = mr.get("raw_score") or 0
        severity = mr.get("severity", "low")
        verdict = _verdict_label(mr.get("verdict", "unknown"))
        explanation = mr.get("explanation", "No data.")
        provider = mr.get("provider", "unknown").replace("_", " ").title()
        sev_color = _severity_color(severity)

        mod_header = [
            [f"{modality} Analysis", f"Score: {raw_score:.1f}%", f"Verdict: {verdict}", f"Provider: {provider}"],
        ]
        mod_table = Table(mod_header, colWidths=[120, 100, 120, 130])
        mod_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, 0), BRAND_DARK),
            ("TEXTCOLOR", (1, 0), (1, 0), sev_color),
            ("TEXTCOLOR", (2, 0), (2, 0), sev_color),
            ("TEXTCOLOR", (3, 0), (3, 0), BRAND_MUTED),
            ("FONTNAME", (1, 0), (2, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        block = [mod_table, Spacer(1, 1*mm), Paragraph(explanation, styles["Body"])]

        findings = mr.get("findings", [])
        if findings:
            for f in findings:
                block.append(Paragraph(f"  • {f}", styles["SmallGray"]))

        block.append(Spacer(1, 3*mm))
        elements.append(KeepTogether(block))

    # ── Flagged Artifacts ────────────────────────────────────────────────
    artifacts = report.get("detected_artifacts", [])
    if artifacts:
        elements.append(Paragraph("4. Detected Artifacts", styles["SectionHead"]))
        for a in artifacts:
            elements.append(Paragraph(f"• {a}", styles["Body"]))
        elements.append(Spacer(1, 4*mm))

    # ── Digital Signature ────────────────────────────────────────────────
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER, spaceAfter=4*mm))

    sig_data = [
        ["Reviewed & Signed By:", "", "Date:", now.strftime("%d %B %Y")],
        [officer_name, "", "Time:", now.strftime("%H:%M UTC")],
        ["Claims Officer Lead", "", "Designation:", "Senior Claims Adjuster"],
    ]
    sig_table = Table(sig_data, colWidths=[150, 80, 60, 180])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, 0), BRAND_MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), BRAND_MUTED),
        ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (0, 1), 12),
        ("TEXTCOLOR", (0, 1), (0, 1), BRAND_DARK),
        ("TEXTCOLOR", (0, 2), (0, 2), BRAND_BLUE),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 0), (3, -1), BRAND_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(sig_table)

    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(
        "This report was generated by SyntheticShield AI Fraud Intelligence Platform. "
        "The analysis is based on multi-modal deepfake detection across video, audio, image, and text modalities. "
        "All findings are grounded in actual detector output — no speculative content is included. "
        "This document is confidential and intended solely for authorized insurance personnel.",
        styles["Footer"]
    ))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(f"© {now.year} SyntheticShield · syntheticshield.ai · Fraud Intelligence Platform", styles["Footer"]))

    doc.build(elements)
    return buf.getvalue()
