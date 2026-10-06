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
    RESEMBLE_AI_API_KEY: str = ""

    # Copilot LLM (provider-swappable)
    COPILOT_LLM_PROVIDER: str = "mistral"  # mistral | gemini | mock
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"
    SERPAPI_API_KEY: str = ""

    # Fraud Fusion Scoring — provider selection (spec §9)
    AUDIO_DETECTOR_PROVIDER: str = "resemble"   # resemble | mock
    TEXT_DETECTOR_PRIMARY: str = "gptzero"      # gptzero | mock
    TEXT_DETECTOR_SECONDARY: str = "pangram"    # pangram | mock | none
    REVERSE_SEARCH_PROVIDER: str = "serpapi"    # serpapi | mock
    PART_PRICING_PROVIDER: str = "serpapi"      # serpapi | mock
    WEATHER_PROVIDER: str = "openweather"       # openweather | mock
    STT_PROVIDER: str = "faster_whisper"        # faster_whisper | mock | none
    SCORING_DEMO_MODE: int = 0                  # 1 = force all mock providers
    RESUME_INTERRUPTED_CLAIMS: bool = True      # re-run claims left in "processing" at startup
    GPTZERO_API_KEY: str = ""
    PANGRAM_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""

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
