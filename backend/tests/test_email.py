"""Verification email delivery: which provider is used, and what happens
when none is. A signup page that says "code sent" when nothing was sent is
the failure this guards against."""

from contextlib import contextmanager

import pytest

import utils
from config import settings


@contextmanager
def patched(obj, **values):
    """Set attributes for the duration of a block, then put them back."""
    before = {name: getattr(obj, name) for name in values}
    for name, value in values.items():
        setattr(obj, name, value)
    try:
        yield
    finally:
        for name, value in before.items():
            setattr(obj, name, value)

NONE = dict(BREVO_API_KEY="", RESEND_API_KEY="", EMAIL_PASSWORD="", EMAIL_FROM="")


def test_provider_precedence():
    with patched(settings, **{**NONE, "EMAIL_FROM": "a@b.co", "EMAIL_PASSWORD": "pw"}):
        assert utils.email_provider() == "smtp"
    with patched(settings, **{**NONE, "EMAIL_FROM": "a@b.co", "EMAIL_PASSWORD": "pw", "RESEND_API_KEY": "re"}):
        assert utils.email_provider() == "resend"
    with patched(settings, **{**NONE, "EMAIL_FROM": "a@b.co", "RESEND_API_KEY": "re", "BREVO_API_KEY": "br"}):
        assert utils.email_provider() == "brevo"
    with patched(settings, **NONE):
        assert utils.email_provider() == "none"
    # A key with no sender address cannot send anything.
    with patched(settings, **{**NONE, "BREVO_API_KEY": "br"}):
        assert utils.email_provider() == "none"


def test_production_refuses_to_pretend_it_sent():
    with patched(settings, IS_PRODUCTION=True, **NONE):
        with pytest.raises(utils.EmailDeliveryError):
            utils.send_otp_email("user@example.com", "123456")


def test_development_logs_instead_of_failing():
    with patched(settings, IS_PRODUCTION=False, **NONE):
        utils.send_otp_email("user@example.com", "123456")  # must not raise


def test_brevo_payload_and_error_handling():
    sent = {}

    class Reply:
        status_code = 201
        text = ""

    def post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, json=json)
        return Reply()

    with patched(utils.requests, post=post), patched(
        settings, **{**NONE, "BREVO_API_KEY": "key", "EMAIL_FROM": "noreply@x.co"}
    ):
        utils.send_otp_email("user@example.com", "123456")

    assert sent["url"] == "https://api.brevo.com/v3/smtp/email"
    assert sent["headers"]["api-key"] == "key"
    assert sent["json"]["to"] == [{"email": "user@example.com"}]
    assert sent["json"]["sender"]["email"] == "noreply@x.co"
    assert "123456" in sent["json"]["textContent"]

    class Rejected:
        status_code = 401
        text = "unauthorized"

    with patched(utils.requests, post=lambda *a, **k: Rejected()), patched(
        settings, **{**NONE, "BREVO_API_KEY": "bad", "EMAIL_FROM": "noreply@x.co"}
    ):
        with pytest.raises(utils.EmailDeliveryError):
            utils.send_otp_email("user@example.com", "123456")


def test_network_failure_becomes_a_delivery_error():
    def post(*args, **kwargs):
        raise ConnectionError("no route")

    with patched(utils.requests, post=post), patched(
        settings, **{**NONE, "RESEND_API_KEY": "key", "EMAIL_FROM": "noreply@x.co"}
    ):
        with pytest.raises(utils.EmailDeliveryError):
            utils.send_otp_email("user@example.com", "123456")
