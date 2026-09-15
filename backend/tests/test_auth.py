import pytest
from fastapi import HTTPException

from auth import (
    ACCESS,
    REFRESH,
    decode_token,
    hash_password,
    verify_password,
)
from config import settings
from jose import jwt


def test_password_hashing_roundtrip():
    hashed = hash_password("correct horse battery")
    assert hashed != "correct horse battery"
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong", hashed)


def _token(sub, ttype):
    import time

    return jwt.encode(
        {"sub": sub, "type": ttype, "exp": int(time.time()) + 60, "jti": "x"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def test_access_token_decodes():
    payload = decode_token(_token("kavita", ACCESS), ACCESS)
    assert payload["sub"] == "kavita"


def test_refresh_token_cannot_be_used_as_access_token():
    with pytest.raises(HTTPException) as exc:
        decode_token(_token("kavita", REFRESH), ACCESS)
    assert exc.value.status_code == 401


def test_tampered_token_is_rejected():
    forged = jwt.encode({"sub": "victim", "type": ACCESS}, "attacker-secret")
    with pytest.raises(HTTPException) as exc:
        decode_token(forged, ACCESS)
    assert exc.value.status_code == 401
