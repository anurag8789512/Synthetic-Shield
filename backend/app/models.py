from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    dob = Column(String, nullable=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    policies = relationship("Policy", back_populates="user")


class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    policy_number = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, nullable=False, default="active")
    issued_date = Column(String, nullable=True)
    renewal_date = Column(String, nullable=True)

    user = relationship("User", back_populates="policies")
    coverages = relationship("Coverage", back_populates="policy")


class Coverage(Base):
    __tablename__ = "coverages"
    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), index=True)
    coverage_type = Column(String, nullable=False)
    coverage_label = Column(String, nullable=False)
    coverage_limit_cents = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="active")

    policy = relationship("Policy", back_populates="coverages")


class OTPCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, index=True)  # holds a users.id or claims_officers.id depending on owner_type
    owner_type = Column(String, nullable=False, default="user")  # "user" | "officer"
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True, index=True)
    claim_number = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    policy_id = Column(Integer, ForeignKey("policies.id"))
    coverage_id = Column(Integer, ForeignKey("coverages.id"))
    accident_location = Column(String)
    accident_description = Column(Text)
    incident_at = Column(DateTime, nullable=True)  # claimant-reported, local time
    video_url = Column(String)
    image_url = Column(String)
    audio_url = Column(String)
    transcript_text = Column(Text)
    status = Column(String, nullable=False, default="processing")
    fraud_confidence_score = Column(Float, nullable=True)
    consistency_score = Column(Float, nullable=True)
    narrative_similarity_score = Column(Float, nullable=True)
    artifact_report = Column(Text, nullable=True)
    claim_amount_cents = Column(Integer, nullable=True)
    valuation_report = Column(Text, nullable=True)
    payout_transaction_id = Column(String, nullable=True)
    payout_amount_cents = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClaimDocument(Base):
    __tablename__ = "claim_documents"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    file_url = Column(String, nullable=False)
    file_type = Column(String, nullable=False, default="pdf")
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class ClaimMediaAnalysis(Base):
    __tablename__ = "claim_media_analysis"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), index=True)
    modality = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    raw_score = Column(Float, nullable=True)
    findings_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClaimsOfficer(Base):
    __tablename__ = "claims_officers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    password_hash = Column(String, nullable=True)
    role = Column(String, nullable=False)
    department = Column(String, nullable=True)


class ModeratorAction(Base):
    __tablename__ = "moderator_actions"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    officer_id = Column(Integer, ForeignKey("claims_officers.id"))
    decision = Column(String, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    decided_at = Column(DateTime, default=datetime.utcnow)


class SIUReview(Base):
    __tablename__ = "siu_reviews"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), unique=True)
    required_votes = Column(Integer, nullable=False, default=5)
    status = Column(String, nullable=False, default="pending")


class SIUOfficerVote(Base):
    __tablename__ = "siu_officer_votes"
    id = Column(Integer, primary_key=True, index=True)
    siu_review_id = Column(Integer, ForeignKey("siu_reviews.id"))
    officer_id = Column(Integer, ForeignKey("claims_officers.id"))
    vote = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    voted_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("siu_review_id", "officer_id"),)


class Payout(Base):
    __tablename__ = "payouts"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    amount_cents = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    transaction_id = Column(String, nullable=True)
    initiated_at = Column(DateTime, default=datetime.utcnow)


class NotificationLog(Base):
    __tablename__ = "notifications_log"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    channel = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    template_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    provider_message_id = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)


class AuditTrail(Base):
    __tablename__ = "audit_trail"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), index=True)
    actor_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CopilotMessage(Base):
    __tablename__ = "copilot_messages"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), index=True)
    officer_id = Column(Integer, ForeignKey("claims_officers.id"))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClaimAssignment(Base):
    __tablename__ = "claim_assignments"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), index=True)
    officer_id = Column(Integer, ForeignKey("claims_officers.id"), index=True)
    assignment_type = Column(String, nullable=False)  # "siu_vote" | "moderator_review"
    status = Column(String, nullable=False, default="pending")  # pending | completed
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
