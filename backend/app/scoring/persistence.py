"""Append-only persistence for scoring results (spec §7).

claim_scores / score_findings / evidence_hashes are INSERT-only; SQLAlchemy
event listeners raise on any UPDATE or DELETE of these models.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Session as DBSession

from app.database import Base
from app.scoring.models import Finding, ScoreBreakdown


class ClaimScore(Base):
    __tablename__ = "claim_scores"
    __table_args__ = (UniqueConstraint("claim_id", "version", name="uq_claim_score_version"),)
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True, nullable=False)
    version = Column(Integer, nullable=False)
    config_version = Column(String, nullable=False)
    base_score = Column(Float, nullable=False)
    final_score = Column(Float, nullable=False)
    escalated = Column(Integer, nullable=False, default=0)
    escalation_source = Column(String, nullable=True)
    routing_band = Column(String, nullable=False)
    forced_review_reason = Column(String, nullable=True)
    payout_cap = Column(Float, nullable=True)
    breakdown_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScoreFinding(Base):
    __tablename__ = "score_findings"
    id = Column(Integer, primary_key=True, index=True)
    claim_score_id = Column(Integer, ForeignKey("claim_scores.id"), index=True, nullable=False)
    rule_id = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    points = Column(Float, nullable=False)
    file_id = Column(String, nullable=True)
    human_readable = Column(Text, nullable=False)
    extra_json = Column(Text, nullable=True)


class EvidenceHash(Base):
    __tablename__ = "evidence_hashes"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(String, index=True, nullable=False)
    file_id = Column(String, nullable=False)
    sha256 = Column(String, index=True, nullable=False)
    phash = Column(String, index=True, nullable=True)
    media_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppendOnlyViolation(RuntimeError):
    pass


def _forbid(mapper, connection, target):  # noqa: ARG001
    raise AppendOnlyViolation(
        f"{type(target).__name__} rows are append-only; UPDATE/DELETE is forbidden"
    )


for _model in (ClaimScore, ScoreFinding, EvidenceHash):
    event.listen(_model, "before_update", _forbid)
    event.listen(_model, "before_delete", _forbid)


def next_version(db: DBSession, claim_id: str) -> int:
    latest = (
        db.query(ClaimScore.version)
        .filter(ClaimScore.claim_id == str(claim_id))
        .order_by(ClaimScore.version.desc())
        .first()
    )
    return (latest[0] + 1) if latest else 1


def save_breakdown(db: DBSession, breakdown: ScoreBreakdown) -> ClaimScore:
    row = ClaimScore(
        claim_id=str(breakdown.claim_id),
        version=breakdown.version,
        config_version=breakdown.config_version,
        base_score=breakdown.base_score,
        final_score=breakdown.final_score,
        escalated=1 if breakdown.escalated else 0,
        escalation_source=breakdown.escalation_source,
        routing_band=breakdown.routing_band,
        forced_review_reason=breakdown.forced_review_reason,
        payout_cap=breakdown.payout_cap,
        breakdown_json=breakdown.model_dump_json(),
        created_at=breakdown.created_at,
    )
    db.add(row)
    db.flush()  # obtain row.id for findings FK
    for sub in breakdown.subscores:
        for f in sub.findings:
            db.add(ScoreFinding(
                claim_score_id=row.id,
                rule_id=f.rule_id,
                severity=f.severity,
                points=f.points,
                file_id=f.file_id,
                human_readable=f.human_readable,
                extra_json=json.dumps(f.extra) if f.extra else None,
            ))
    db.commit()
    return row


def record_evidence_hash(db: DBSession, claim_id: str, file_id: str,
                         sha256: str, phash: str | None, media_type: str) -> None:
    db.add(EvidenceHash(claim_id=str(claim_id), file_id=file_id, sha256=sha256,
                        phash=phash, media_type=media_type))
    db.commit()


def find_hash_matches(db: DBSession, claim_id: str, sha256: str,
                      phash: str | None, phash_threshold: int) -> list[EvidenceHash]:
    """Exact SHA-256 or pHash (hamming <= threshold) matches from OTHER claims."""
    matches: list[EvidenceHash] = []
    exact = (
        db.query(EvidenceHash)
        .filter(EvidenceHash.sha256 == sha256, EvidenceHash.claim_id != str(claim_id))
        .all()
    )
    matches.extend(exact)
    if phash:
        candidates = (
            db.query(EvidenceHash)
            .filter(EvidenceHash.claim_id != str(claim_id), EvidenceHash.phash.isnot(None))
            .all()
        )
        seen = {m.id for m in matches}
        for cand in candidates:
            if cand.id in seen:
                continue
            if _hamming_hex(phash, cand.phash) <= phash_threshold:
                matches.append(cand)
    return matches


def _hamming_hex(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (ValueError, TypeError):
        return 999
