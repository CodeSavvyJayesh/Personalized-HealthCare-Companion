"""Request/response models.

Replaces `data = await request.json(); data.get("thing")`. Three wins:
real validation at the edge, automatic OpenAPI docs, and endpoints that can
be plain `def` (FastAPI then runs them in a threadpool, so the blocking
pymongo and requests calls no longer stall the event loop).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ------------------------------------------------------------------- auth
class SignupIn(BaseModel):
    username: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    session_id: str


class RefreshIn(BaseModel):
    refresh_token: str


class EmailIn(BaseModel):
    email: EmailStr


class VerifyOtpIn(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)
    password: str = Field(min_length=8, max_length=128)


class ResetPasswordIn(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)


# ------------------------------------------------------------------- chat
class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = "en-US"
    session_id: str


class ClassifyIn(BaseModel):
    """Input to /safety/classify. Not stored anywhere."""

    text: str = Field(min_length=1, max_length=4000)


class ChatOut(BaseModel):
    reply: str
    sentiment: str
    risk_tier: str
    resources_shown: bool
    session_id: str


# ---------------------------------------------------------------- content
class JournalIn(BaseModel):
    mood: str | None = None
    content: str = Field(min_length=1, max_length=20000)


class MoodIn(BaseModel):
    mood: str = Field(min_length=1, max_length=64)
    intensity: int | None = Field(default=None, ge=0, le=10)
    energy: int | None = Field(default=None, ge=0, le=10)
    tags: list[str] = Field(default_factory=list, max_length=20)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str | None = None


class TaskUpdateIn(BaseModel):
    completed: bool


class SleepIn(BaseModel):
    bed_time: str = Field(pattern=r"^\d{1,2}:\d{2}$")
    wake_time: str = Field(pattern=r"^\d{1,2}:\d{2}$")
    quality: int | None = Field(default=None, ge=1, le=5)


class PostIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str | None = None


class GoalUpdateIn(BaseModel):
    completed: bool


class OkOut(BaseModel):
    success: bool = True


Sentiment = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
