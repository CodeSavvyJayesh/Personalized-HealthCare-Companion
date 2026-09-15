"""Authentication and authorization.

Before: every endpoint trusted a `user_id` that the caller typed into the
URL or the request body. `GET /journals/someone-else` returned someone
else's private journal.

Now: the caller proves who they are with a signed access token, and
`require_owner` refuses any request whose path user_id is not the token's
subject. Authorization is enforced server-side, never by the client.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings
from db import refresh_tokens_collection, users_collection

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

ACCESS = "access"
REFRESH = "refresh"


def utcnow() -> datetime:
    """Timezone-aware UTC. `datetime.utcnow()` is deprecated and returns a
    naive datetime, which silently breaks comparisons against tz-aware
    values coming back from Mongo."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- passwords


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(raw, hashed)
    except Exception:
        return False


# ------------------------------------------------------------------ tokens


def _encode(subject: str, token_type: str, expires: timedelta, jti: str) -> str:
    now = utcnow()
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": jti,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(username: str) -> str:
    return _encode(
        username,
        ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        uuid.uuid4().hex,
    )


def create_refresh_token(username: str) -> str:
    """Refresh tokens are persisted so they can be revoked on logout.
    A stateless refresh token you cannot revoke is not a logout."""
    jti = uuid.uuid4().hex
    expires = timedelta(days=settings.REFRESH_TOKEN_DAYS)
    token = _encode(username, REFRESH, expires, jti)
    refresh_tokens_collection.insert_one(
        {
            "jti": jti,
            "user_id": username,
            "created_at": utcnow(),
            "expires_at": utcnow() + expires,
        }
    )
    return token


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type"
        )
    return payload


def revoke_refresh_token(jti: str) -> None:
    refresh_tokens_collection.delete_one({"jti": jti})


def refresh_is_active(jti: str) -> bool:
    return refresh_tokens_collection.find_one({"jti": jti}) is not None


# ------------------------------------------------------------ dependencies


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Returns the authenticated username, or raises 401."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials, ACCESS)
    username = payload.get("sub")
    if not username or not users_collection.find_one({"username": username}):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user"
        )
    return username


def require_owner(
    user_id: str = Path(...),
    current_user: str = Depends(get_current_user),
) -> str:
    """For routes shaped `/thing/{user_id}`: the path must match the token.

    This is the fix for the IDOR. The user_id in the URL is now decorative —
    it has to agree with the token or the request is rejected.
    """
    if user_id != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own data",
        )
    return current_user
