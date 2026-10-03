"""Central configuration. Every secret comes from the environment.

Nothing in this file may contain a credential. If a required secret is
missing the app refuses to start rather than falling back to a default —
a silent insecure default is worse than a crash.
"""

import os
import sys
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        sys.exit(
            f"FATAL: required environment variable {name} is not set. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    # ---------- environment ----------
    ENV: str = os.getenv("ENV", "development")
    IS_PRODUCTION: bool = ENV == "production"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ---------- database ----------
    MONGO_URI: str = _required("MONGO_URI")
    MONGO_DB: str = os.getenv("MONGO_DB", "health_app")
    # Some ISP/router resolvers (and most corporate networks) don't return
    # SRV records, which is exactly what a mongodb+srv:// URI needs. Pointing
    # dnspython at a public resolver is the standard workaround. Set
    # DNS_NAMESERVERS empty to use the system resolver instead.
    DNS_NAMESERVERS: list[str] = _csv("DNS_NAMESERVERS", "8.8.8.8,1.1.1.1")

    # ---------- auth ----------
    JWT_SECRET: str = _required("JWT_SECRET")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_MINUTES: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
    REFRESH_TOKEN_DAYS: int = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
    # POST /signup creates an account with no email verification. That is
    # useful for local development and the smoke test, and a hole in
    # production, where the only door should be the OTP flow.
    ALLOW_DIRECT_SIGNUP: bool = (
        os.getenv("ALLOW_DIRECT_SIGNUP", "false" if IS_PRODUCTION else "true").lower()
        == "true"
    )

    # ---------- cors ----------
    CORS_ORIGINS: list[str] = _csv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )

    # ---------- llm ----------
    # Any OpenAI-compatible endpoint: Ollama, vLLM, Groq, OpenAI, Together...
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL", "http://127.0.0.1:11434/v1"
    ).rstrip("/")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama3:8b")
    # Tried when the main model is rate limited. Hosted free tiers meter each
    # model separately, so a smaller model is usually still available.
    LLM_FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # ---------- sentiment ----------
    SENTIMENT_MODEL_PATH: str = os.getenv("SENTIMENT_MODEL_PATH", "./models")
    # auto | onnx | torch | off — see sentiment.py
    SENTIMENT_BACKEND: str = os.getenv("SENTIMENT_BACKEND", "auto").lower()
    SENTIMENT_ONNX_FILE: str = os.getenv("SENTIMENT_ONNX_FILE", "model.onnx")
    # Below this confidence the binary SST-2 head is not actually telling us
    # anything, so we call it NEUTRAL instead of forcing a polarity.
    SENTIMENT_NEUTRAL_THRESHOLD: float = float(
        os.getenv("SENTIMENT_NEUTRAL_THRESHOLD", "0.80")
    )

    # ---------- translation ----------
    # auto   Google (via deep-translator) first, the LLM if that fails
    # google deep-translator only
    # llm    the configured LLM only
    # off    no translation; text is passed through untouched
    TRANSLATION_PROVIDER: str = os.getenv("TRANSLATION_PROVIDER", "auto").lower()

    # ---------- memory ----------
    CHAT_WINDOW_TURNS: int = int(os.getenv("CHAT_WINDOW_TURNS", "12"))
    SUMMARISE_AFTER_TURNS: int = int(os.getenv("SUMMARISE_AFTER_TURNS", "20"))

    # ---------- email / otp ----------
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "MindWell")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
    # HTTP email APIs. Many hosts (Render's free tier among them) block
    # outbound SMTP ports entirely, so SMTP alone is not deployable there.
    # If either key is set it is used instead of SMTP.
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    OTP_TTL_SECONDS: int = int(os.getenv("OTP_TTL_SECONDS", "300"))

    # ---------- rate limiting ----------
    RATE_LIMIT_CHAT: int = int(os.getenv("RATE_LIMIT_CHAT", "30"))
    RATE_LIMIT_AUTH: int = int(os.getenv("RATE_LIMIT_AUTH", "10"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    # ---------- safety ----------
    CRISIS_REGION: str = os.getenv("CRISIS_REGION", "IN")

    # ---------- health twin ----------
    # Offset used to decide what "today" means for daily scores.
    # 330 = IST (UTC+5:30).
    TZ_OFFSET_MINUTES: int = int(os.getenv("TZ_OFFSET_MINUTES", "330"))


def _check_production(s: Settings) -> None:
    """Refuse to boot a production instance with development-grade settings."""
    if not s.IS_PRODUCTION:
        return
    problems = []
    if len(s.JWT_SECRET) < 32:
        problems.append("JWT_SECRET must be at least 32 characters in production")
    if "127.0.0.1" in s.LLM_BASE_URL or "localhost" in s.LLM_BASE_URL:
        problems.append(
            "LLM_BASE_URL points at this machine; a deployed instance needs a "
            "hosted OpenAI-compatible endpoint (see .env.example)"
        )
    if problems:
        sys.exit("FATAL: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _check_production(s)
    return s


settings = get_settings()
