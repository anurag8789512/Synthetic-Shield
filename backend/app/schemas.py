from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── Auth ───────────────────────────────────────────────────────────────────────
class OTPRequest(BaseModel):
    identifier: str  # phone or email


class OTPResponse(BaseModel):
    message: str
    debug_otp: Optional[str] = None


class OTPVerify(BaseModel):
    identifier: str
    code: str


class OTPVerifyResponse(BaseModel):
    session_token: str
    user_id: int
    full_name: str


# ── Dashboard Auth ─────────────────────────────────────────────────────────────
class DashboardLoginRequest(BaseModel):
    email: str
    password: str


class DashboardLoginResponse(BaseModel):
    session_token: str
    officer_id: int
    name: str
    role: str


# ── Policy ─────────────────────────────────────────────────────────────────────
class CoverageOut(BaseModel):
    id: int
    coverage_type: str
    coverage_label: str
    coverage_limit_cents: Optional[int]
    status: str

    class Config:
        from_attributes = True


class PolicyOut(BaseModel):
    id: int
    policy_number: str
    status: str
    issued_date: Optional[str]
    renewal_date: Optional[str]
    coverages: list[CoverageOut] = []

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    full_name: str
    email: Optional[str]
    phone: Optional[str]

    class Config:
        from_attributes = True
