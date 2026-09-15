"""Email + OTP.

OTPs used to live in a module-level dict, which meant they vanished on
every restart and were invisible to any second worker. They now live in
Mongo with a TTL index, so expiry is enforced by the database and no
cleanup job is required.

SMTP is synchronous here on purpose: the endpoints that call it are plain
`def`, so FastAPI already runs them in a threadpool.
"""

from __future__ import annotations

import logging
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from auth import utcnow
from config import settings
from db import otp_collection

log = logging.getLogger(__name__)


def generate_otp() -> str:
    return str(secrets.randbelow(1_000_000)).zfill(6)


def store_otp(email: str, otp: str) -> None:
    otp_collection.update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "otp": otp,
                "created_at": utcnow(),
                "expires_at": utcnow() + timedelta(seconds=settings.OTP_TTL_SECONDS),
                "attempts": 0,
            }
        },
        upsert=True,
    )


def verify_otp(email: str, otp: str) -> bool:
    """Single-use, attempt-limited, expiry enforced by the TTL index."""
    record = otp_collection.find_one({"email": email})
    if not record:
        return False
    if record.get("attempts", 0) >= 5:
        otp_collection.delete_one({"email": email})
        return False
    if not secrets.compare_digest(str(record.get("otp", "")), str(otp)):
        otp_collection.update_one({"email": email}, {"$inc": {"attempts": 1}})
        return False
    otp_collection.delete_one({"email": email})
    return True


def send_otp_email(to_email: str, otp: str) -> None:
    if not settings.EMAIL_FROM or not settings.EMAIL_PASSWORD:
        # In development, don't hard-fail the signup flow just because SMTP
        # isn't configured — log it so the flow stays testable.
        log.warning("SMTP not configured. OTP for %s is %s", to_email, otp)
        return

    msg = EmailMessage()
    msg["Subject"] = "Your MindWell verification code"
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Your MindWell verification code is: {otp}\n\n"
        f"It expires in {settings.OTP_TTL_SECONDS // 60} minutes.\n"
        "If you didn't request this, you can ignore this email."
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(settings.EMAIL_FROM, settings.EMAIL_PASSWORD)
        server.send_message(msg)
