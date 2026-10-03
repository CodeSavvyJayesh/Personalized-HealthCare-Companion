"""Email + OTP.

OTPs used to live in a module-level dict, which meant they vanished on
every restart and were invisible to any second worker. They now live in
Mongo with a TTL index, so expiry is enforced by the database and no
cleanup job is required.

Sending is synchronous on purpose: the endpoints that call it are plain
`def`, so FastAPI already runs them in a threadpool.

Three ways to deliver, picked by what is configured:

    BREVO_API_KEY   Brevo's HTTPS API
    RESEND_API_KEY  Resend's HTTPS API
    EMAIL_PASSWORD  plain SMTP (Gmail app password, etc.)

The HTTPS providers exist because SMTP is not an option on many hosts:
Render's free tier, for one, blocks outbound ports 25, 465 and 587
outright, and Gmail throttles logins from datacentre IPs. An OTP that
never arrives is a signup page that does not work.
"""

from __future__ import annotations

import logging
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

import requests

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
    # Checked here as well as by the TTL index: Mongo's TTL sweep only runs
    # about once a minute, and the index itself is created best-effort.
    expires_at = record.get("expires_at")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=utcnow().tzinfo)
        if expires_at < utcnow():
            otp_collection.delete_one({"email": email})
            return False
    if record.get("attempts", 0) >= 5:
        otp_collection.delete_one({"email": email})
        return False
    if not secrets.compare_digest(str(record.get("otp", "")), str(otp)):
        otp_collection.update_one({"email": email}, {"$inc": {"attempts": 1}})
        return False
    otp_collection.delete_one({"email": email})
    return True


class EmailDeliveryError(RuntimeError):
    """The message could not be handed to any provider."""


def email_provider() -> str:
    """Which delivery path is configured: brevo | resend | smtp | none."""
    if settings.BREVO_API_KEY and settings.EMAIL_FROM:
        return "brevo"
    if settings.RESEND_API_KEY and settings.EMAIL_FROM:
        return "resend"
    if settings.EMAIL_FROM and settings.EMAIL_PASSWORD:
        return "smtp"
    return "none"


def _send_brevo(to_email: str, subject: str, body: str) -> None:
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
        json={
            "sender": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body,
        },
        timeout=15,
    )
    if response.status_code >= 300:
        raise EmailDeliveryError(f"Brevo {response.status_code}: {response.text[:200]}")


def _send_resend(to_email: str, subject: str, body: str) -> None:
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        },
        timeout=15,
    )
    if response.status_code >= 300:
        raise EmailDeliveryError(f"Resend {response.status_code}: {response.text[:200]}")


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
    msg["To"] = to_email
    msg.set_content(body)

    # Gmail shows app passwords in groups of four; the spaces are not part
    # of the password.
    password = settings.EMAIL_PASSWORD.replace(" ", "")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(settings.EMAIL_FROM, password)
        server.send_message(msg)


def send_otp_email(to_email: str, otp: str) -> None:
    """Deliver the code or raise EmailDeliveryError. Never fails silently in
    production: a signup that claims to have emailed a code it did not send
    is worse than an honest error."""
    subject = "Your MindWell verification code"
    body = (
        f"Your MindWell verification code is: {otp}\n\n"
        f"It expires in {settings.OTP_TTL_SECONDS // 60} minutes.\n"
        "If you didn't request this, you can ignore this email."
    )

    provider = email_provider()
    if provider == "none":
        if settings.IS_PRODUCTION:
            raise EmailDeliveryError("No email provider is configured")
        # Development only: keep the flow testable without any mail setup.
        log.warning("No email provider configured. OTP for %s is %s", to_email, otp)
        return

    sender = {"brevo": _send_brevo, "resend": _send_resend, "smtp": _send_smtp}[provider]
    try:
        sender(to_email, subject, body)
    except EmailDeliveryError:
        raise
    except Exception as exc:
        raise EmailDeliveryError(f"{provider}: {exc}") from exc
    log.info("Verification email sent via %s", provider)
