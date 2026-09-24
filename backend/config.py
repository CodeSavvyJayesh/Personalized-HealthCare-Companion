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
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # ---------- sentiment ----------
    SENTIMENT_MODEL_PATH: str = os.getenv("SENTIMENT_MODEL_PATH", "./models")
    # Below this confidence the binary SST-2 head is not actually telling us
    # anything, so we call it NEUTRAL instead of forcing a polarity.
    SENTIMENT_NEUTRAL_THRESHOLD: float = float(
        os.getenv("SENTIMENT_NEUTRAL_THRESHOLD", "0.80")
    )

    # ---------- memory ----------
    CHAT_WINDOW_TURNS: int = int(os.getenv("CHAT_WINDOW_TURNS", "12"))
    SUMMARISE_AFTER_TURNS: int = int(os.getenv("SUMMARISE_AFTER_TURNS", "20"))

    # ---------- email / otp ----------
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
