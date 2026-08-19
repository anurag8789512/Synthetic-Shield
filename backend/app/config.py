from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Storage
    STORAGE_PROVIDER: Literal["local", "s3", "supabase"] = "local"
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Detection providers
    VIDEO_DETECTION_PROVIDER: str = "mock"
    AUDIO_DETECTION_PROVIDER: str = "mock"
    IMAGE_DETECTION_PROVIDER: str = "mock"
    TEXT_DETECTION_PROVIDER: str = "mock"
    REALITY_DEFENDER_API_KEY: str = ""

    # Adjudication thresholds
    AUTO_APPROVE_BELOW: int = 15
    SIU_FLAG_ABOVE: int = 85

    # OTP / Auth
    OTP_PROVIDER: Literal["console", "twilio", "email", "fast2sms"] = "console"
    OTP_LENGTH: int = 6
    OTP_EXPIRY_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5
    SESSION_EXPIRY_HOURS: int = 12
    FAST2SMS_API_KEY: str = ""
    TWOFACTOR_API_KEY: str = ""
    RESEND_API_KEY: str = ""

    # Misc
    DETECTION_SIMULATED_DELAY_SECONDS: int = 4
    DATABASE_URL: str = "sqlite:///./claims.db"
    CORS_ORIGINS: str = "http://localhost:8443,http://localhost:3000,http://localhost:3001,http://localhost:5173"
    MOCK_PAYOUT_AMOUNT_CENTS: int = 125000

    class Config:
        env_file = ".env"
        extra = "ignore"
        # Prevent .env from overriding CORS since it may be stale
        env_prefix_priority = "config"


settings = Settings()
