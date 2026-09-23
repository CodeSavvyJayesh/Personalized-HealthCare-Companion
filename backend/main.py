"""MindWell API.

Every data route is authenticated and scoped to the caller. Nothing trusts
a user_id supplied by the client.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from bson import ObjectId
from bson.errors import InvalidId
from deep_translator import GoogleTranslator
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

import llm
import memory
import safety
import sentiment
from analytic import router as analytic_router
from fitness import router as fitness_router
from safety_api import router as safety_router
from auth import (
    REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    refresh_is_active,
    require_owner,
    revoke_refresh_token,
    utcnow,
    verify_password,
)
from config import settings
from db import (
    community_collection,
    ensure_indexes,
    fitness_metrics_collection,
    fitness_plans_collection,
    fitness_profiles_collection,
    fitness_workouts_collection,
    goals_collection,
    journals_collection,
    meditation_collection,
    messages_collection,
    moods_collection,
    ping,
    safety_events_collection,
    sessions_collection,
    sleep_collection,
    tasks_collection,
    users_collection,
)
from ratelimit import limit
from schemas import (
    ChatIn,
    ChatOut,
    EmailIn,
    GoalIn,
    GoalUpdateIn,
    JournalIn,
    LoginIn,
    MoodIn,
    OkOut,
    PostIn,
    RefreshIn,
    ResetPasswordIn,
    SignupIn,
    SleepIn,
    TaskIn,
    TaskUpdateIn,
    TokenOut,
    VerifyOtpIn,
)
from utils import generate_otp, send_otp_email, store_otp, verify_otp

# Root stays at INFO no matter what. DEBUG is opt-in per application logger.
# Setting the ROOT logger to DEBUG turns on every third-party library at once
# — pymongo alone then prints a full replica-set heartbeat for all three
# shards every 10 seconds, which buries the one traceback you need.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_app_level = logging.DEBUG if settings.DEBUG else logging.INFO
for _name in ("mindwell", "main", "auth", "db", "llm", "memory", "safety",
              "sentiment", "analytic", "fitness", "utils", "uvicorn.error"):
    logging.getLogger(_name).setLevel(_app_level)

log = logging.getLogger("mindwell")

auth_limit = limit("auth", settings.RATE_LIMIT_AUTH, settings.RATE_LIMIT_WINDOW)
chat_limit = limit("chat", settings.RATE_LIMIT_CHAT, settings.RATE_LIMIT_WINDOW)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_indexes()
    # Sentiment is an enhancement, not a dependency. A missing model file or
    # a torch problem should degrade the dashboard, not stop the API from
    # serving — including the safety layer, which needs no model at all.
    try:
        sentiment.load_model()
    except Exception as exc:
        log.warning("Sentiment model unavailable, continuing without it: %s", exc)
    llm.warm_up()
    log.info("MindWell API ready (env=%s)", settings.ENV)
    yield


app = FastAPI(
    title="MindWell API",
    version="2.0.0",
    description="Mental health companion API with crisis-aware safety layer.",
    lifespan=lifespan,
    docs_url=None if settings.ENV == "production" else "/docs",
)

# Wildcard origins plus credentials is rejected by browsers anyway and is a
# CSRF footgun. Origins are now an explicit allowlist from the environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(analytic_router)
app.include_router(safety_router)
app.include_router(fitness_router)

SYSTEM_PROMPT = """
You are MindWell, an empathetic, calm, emotionally supportive mental health
companion.

RESPONSE FORMAT:
- Valid Markdown
- **Bold** for emphasis, bullets where they help
- Blank lines between paragraphs

BEHAVIOUR:
- Acknowledge the emotion before anything else
- No judgement, no diagnosis, no medical or medication advice
- You remember what this person has told you earlier in the conversation;
  refer back to it naturally when it is relevant
- Ask at most ONE gentle follow-up question
- Keep replies to 2-8 sentences
"""

LANG_CODE_MAP = {"en-US": "en", "hi-IN": "hi", "mr-IN": "mr"}


# ------------------------------------------------------------------ utils
def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Malformed id")


def _serialise(docs: list[dict]) -> list[dict]:
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


def _own_session(session_id: str, user_id: str) -> dict:
    session = sessions_collection.find_one({"_id": _oid(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    return session


def _translate(text: str, source: str, target: str) -> str:
    if source == target:
        return text
    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception as exc:
        log.warning("Translation %s->%s failed: %s", source, target, exc)
        return text


# ----------------------------------------------------------------- health
@app.get("/health")
def health() -> dict:
    db_ok = ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
        "llm": llm.health(),
        "env": settings.ENV,
    }


# ------------------------------------------------------------------- auth
@app.post("/signup", response_model=OkOut, dependencies=[Depends(auth_limit)])
def signup(payload: SignupIn) -> OkOut:
    if users_collection.find_one({"username": payload.username}):
        # Same shape as success on purpose — don't let signup be used to
        # enumerate which email addresses have accounts.
        raise HTTPException(status_code=409, detail="Could not create account")
    users_collection.insert_one(
        {
            "username": payload.username,
            "password": hash_password(payload.password),
            "created_at": utcnow(),
        }
    )
    return OkOut()


@app.post("/login", response_model=TokenOut, dependencies=[Depends(auth_limit)])
def login(payload: LoginIn) -> TokenOut:
    user = users_collection.find_one({"username": payload.username})
    if not user or not verify_password(payload.password, user.get("password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    result = sessions_collection.insert_one(
        {"user_id": payload.username, "created_at": utcnow()}
    )
    return TokenOut(
        access_token=create_access_token(payload.username),
        refresh_token=create_refresh_token(payload.username),
        user_id=payload.username,
        session_id=str(result.inserted_id),
    )


@app.post("/auth/refresh", dependencies=[Depends(auth_limit)])
def refresh(payload: RefreshIn) -> dict:
    claims = decode_token(payload.refresh_token, REFRESH)
    if not refresh_is_active(claims["jti"]):
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    return {
        "access_token": create_access_token(claims["sub"]),
        "token_type": "bearer",
    }


@app.post("/auth/logout", response_model=OkOut)
def logout(payload: RefreshIn, _: str = Depends(get_current_user)) -> OkOut:
    try:
        claims = decode_token(payload.refresh_token, REFRESH)
        revoke_refresh_token(claims["jti"])
    except HTTPException:
        pass
    return OkOut()


@app.get("/auth/me")
def me(current_user: str = Depends(get_current_user)) -> dict:
    return {"user_id": current_user}


# -------------------------------------------------------------------- otp
@app.post("/send-otp", response_model=OkOut, dependencies=[Depends(auth_limit)])
def send_otp(payload: EmailIn) -> OkOut:
    otp = generate_otp()
    store_otp(payload.email, otp)
    send_otp_email(payload.email, otp)
    return OkOut()


@app.post("/verify-otp", response_model=OkOut, dependencies=[Depends(auth_limit)])
def verify_signup_otp(payload: VerifyOtpIn) -> OkOut:
    if not verify_otp(payload.email, payload.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    # Previously this inserted unconditionally, so verifying twice created a
    # duplicate account for the same email.
    users_collection.update_one(
        {"username": payload.email},
        {
            "$set": {"password": hash_password(payload.password)},
            "$setOnInsert": {"username": payload.email, "created_at": utcnow()},
        },
        upsert=True,
    )
    return OkOut()


@app.post("/send-reset-otp", response_model=OkOut, dependencies=[Depends(auth_limit)])
def send_reset_otp(payload: EmailIn) -> OkOut:
    if users_collection.find_one({"username": payload.email}):
        otp = generate_otp()
        store_otp(payload.email, otp)
        send_otp_email(payload.email, otp)
    # Always report success: a different answer for unknown emails is an
    # account enumeration oracle.
    return OkOut()


@app.post("/reset-password", response_model=OkOut, dependencies=[Depends(auth_limit)])
def reset_password(payload: ResetPasswordIn) -> OkOut:
    if not verify_otp(payload.email, payload.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    users_collection.update_one(
        {"username": payload.email},
        {"$set": {"password": hash_password(payload.new_password)}},
    )
    return OkOut()


# ------------------------------------------------------------------- chat
@app.get("/chat-history/{session_id}")
def chat_history(session_id: str, current_user: str = Depends(get_current_user)):
    _own_session(session_id, current_user)
    history = list(
        messages_collection.find({"session_id": session_id}).sort("timestamp", 1)
    )
    return {"success": True, "history": _serialise(history)}


@app.post("/chat", response_model=ChatOut, dependencies=[Depends(chat_limit)])
def chat_endpoint(
    payload: ChatIn, current_user: str = Depends(get_current_user)
) -> ChatOut:
    _own_session(payload.session_id, current_user)

    source_lang = LANG_CODE_MAP.get(payload.language, "en")
    user_text = payload.text.strip()
    user_text_en = _translate(user_text, source_lang, "en")

    # ---- 1. SAFETY FIRST, before sentiment, before the model ----------
    assessment = safety.assess_risk(f"{user_text}\n{user_text_en}")

    label, confidence = sentiment.classify(user_text_en)

    messages_collection.insert_one(
        {
            "session_id": payload.session_id,
            "user_id": current_user,
            "sender": "user",
            "text": user_text,
            "sentiment": label,
            "sentiment_confidence": confidence,
            "risk_tier": int(assessment.tier),
            "timestamp": utcnow(),
        }
    )

    resources_shown = False

    if assessment.blocks_llm:
        # Deterministic path. The model is not consulted at all.
        reply = safety.crisis_response(settings.CRISIS_REGION)
        resources_shown = True
        safety.log_safety_event(
            safety_events_collection,
            user_id=current_user,
            session_id=payload.session_id,
            assessment=assessment,
            action="llm_bypassed_crisis_response",
            text_length=len(user_text),
        )
    else:
        history = list(
            messages_collection.find(
                {"session_id": payload.session_id}, {"sender": 1, "text": 1}
            ).sort("timestamp", 1)
        )[:-1]

        summary = memory.load_summary(sessions_collection, payload.session_id)
        summary = memory.maybe_summarise(
            sessions_collection, payload.session_id, history, summary
        )

        system_prompt = SYSTEM_PROMPT
        if assessment.tier >= safety.RiskTier.IDEATION:
            system_prompt = f"{SYSTEM_PROMPT}\n{safety.SAFE_MODE_PROMPT}"

        model_messages = memory.build_messages(
            system_prompt, history, user_text_en, summary
        )

        try:
            reply_en = llm.chat(model_messages, temperature=0.8)
            reply = _translate(reply_en, "en", source_lang)
        except llm.LLMUnavailable:
            reply = (
                "I'm having trouble thinking clearly right now — that's on my "
                "end, not yours. 💙 I'm still here. Could you tell me a little "
                "more about how you're feeling?"
            )

        if assessment.needs_resources:
            reply = safety.append_resources(reply, settings.CRISIS_REGION)
            resources_shown = True
            safety.log_safety_event(
                safety_events_collection,
                user_id=current_user,
                session_id=payload.session_id,
                assessment=assessment,
                action="resources_appended",
                text_length=len(user_text),
            )

    messages_collection.insert_one(
        {
            "session_id": payload.session_id,
            "user_id": current_user,
            "sender": "bot",
            "text": reply,
            "risk_tier": int(assessment.tier),
            "timestamp": utcnow(),
        }
    )

    return ChatOut(
        reply=reply,
        sentiment=label,
        risk_tier=assessment.tier.name,
        resources_shown=resources_shown,
        session_id=payload.session_id,
    )


@app.get("/session-report/{session_id}")
def session_report(session_id: str, current_user: str = Depends(get_current_user)):
    _own_session(session_id, current_user)
    messages = list(messages_collection.find({"session_id": session_id}))

    counts = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}
    for msg in messages:
        if msg.get("sender") != "user":
            continue  # only the user's own words carry their mood
        counts[(msg.get("sentiment") or "NEUTRAL").upper()] = counts.get(
            (msg.get("sentiment") or "NEUTRAL").upper(), 0
        ) + 1

    total = sum(counts.values())
    if total == 0:
        return {
            "total_messages": 0,
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "overall_mood": "NEUTRAL",
            "sentiment_summary": {"Positive": 0, "Negative": 0, "Neutral": 0},
            "insight_message": "Say hello whenever you're ready — there's no rush.",
        }

    overall = "NEUTRAL"
    if counts["NEGATIVE"] > counts["POSITIVE"]:
        overall = "NEGATIVE"
    elif counts["POSITIVE"] > counts["NEGATIVE"]:
        overall = "POSITIVE"

    insight = {
        "POSITIVE": "Your session reflects a lot of positivity. Good to see you feeling well.",
        "NEGATIVE": "It seems you've been sitting with some difficult emotions. Be kind to yourself — one step at a time.",
        "NEUTRAL": "You've had a balanced session today.",
    }[overall]

    return {
        "total_messages": total,
        "positive": counts["POSITIVE"],
        "negative": counts["NEGATIVE"],
        "neutral": counts["NEUTRAL"],
        "overall_mood": overall,
        "sentiment_summary": {
            "Positive": counts["POSITIVE"],
            "Negative": counts["NEGATIVE"],
            "Neutral": counts["NEUTRAL"],
        },
        "insight_message": insight,
    }


# ---------------------------------------------------------------- journal
@app.post("/journal")
def create_journal(payload: JournalIn, current_user: str = Depends(get_current_user)):
    result = journals_collection.insert_one(
        {
            "user_id": current_user,
            "mood": payload.mood,
            "content": payload.content,
            "created_at": utcnow(),
        }
    )
    return {"success": True, "journal_id": str(result.inserted_id)}


@app.get("/journals/{user_id}")
def get_journals(owner: str = Depends(require_owner)):
    docs = list(
        journals_collection.find({"user_id": owner}).sort("created_at", -1)
    )
    return {"success": True, "journals": _serialise(docs)}


# ------------------------------------------------------------------ moods
@app.post("/mood")
def create_mood(payload: MoodIn, current_user: str = Depends(get_current_user)):
    result = moods_collection.insert_one(
        {
            "user_id": current_user,
            "mood": payload.mood,
            "intensity": payload.intensity,
            "energy": payload.energy,
            "tags": payload.tags,
            "created_at": utcnow(),
        }
    )
    return {"success": True, "mood_id": str(result.inserted_id)}


@app.get("/moods/{user_id}")
def get_moods(owner: str = Depends(require_owner)):
    docs = list(moods_collection.find({"user_id": owner}).sort("created_at", -1))
    return {"success": True, "moods": _serialise(docs)}


# ------------------------------------------------------------------ tasks
@app.post("/tasks")
def create_task(payload: TaskIn, current_user: str = Depends(get_current_user)):
    result = tasks_collection.insert_one(
        {
            "user_id": current_user,
            "title": payload.title,
            "category": payload.category,
            "completed": False,
            "created_at": utcnow(),
        }
    )
    return {"success": True, "task_id": str(result.inserted_id)}


@app.get("/tasks/{user_id}")
def get_tasks(owner: str = Depends(require_owner)):
    docs = list(tasks_collection.find({"user_id": owner}).sort("created_at", -1))
    return {"success": True, "tasks": _serialise(docs)}


@app.put("/tasks/{task_id}")
def update_task(
    task_id: str,
    payload: TaskUpdateIn,
    current_user: str = Depends(get_current_user),
):
    # The ownership filter is part of the query, so another user's task id
    # simply matches nothing.
    result = tasks_collection.update_one(
        {"_id": _oid(task_id), "user_id": current_user},
        {"$set": {"completed": payload.completed, "updated_at": utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


@app.put("/tasks/{task_id}/complete")
def complete_task(task_id: str, current_user: str = Depends(get_current_user)):
    result = tasks_collection.update_one(
        {"_id": _oid(task_id), "user_id": current_user},
        {"$set": {"completed": True, "updated_at": utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


# ------------------------------------------------------------- meditation
@app.post("/meditation")
def record_meditation(current_user: str = Depends(get_current_user)):
    today = utcnow().strftime("%Y-%m-%d")
    meditation_collection.update_one(
        {"user_id": current_user, "date": today},
        {"$setOnInsert": {"completed": True, "created_at": utcnow()}},
        upsert=True,
    )
    return {"success": True}


def _streaks(dates: list[str]) -> tuple[int, int]:
    """Returns (current_streak, longest_streak).

    The old version tracked `longest` inside the loop but reset `streak`
    without re-checking the max, so a long early streak followed by a short
    recent one reported the short one.
    """
    if not dates:
        return 0, 0
    unique = sorted(set(dates))
    longest = run = 1
    for i in range(1, len(unique)):
        prev = datetime.strptime(unique[i - 1], "%Y-%m-%d")
        curr = datetime.strptime(unique[i], "%Y-%m-%d")
        run = run + 1 if (curr - prev).days == 1 else 1
        longest = max(longest, run)

    last = datetime.strptime(unique[-1], "%Y-%m-%d").date()
    today = utcnow().date()
    current = run if (today - last) <= timedelta(days=1) else 0
    return current, longest


@app.get("/meditation/{user_id}")
def get_meditation(owner: str = Depends(require_owner)):
    sessions = list(meditation_collection.find({"user_id": owner}).sort("date", 1))
    current, longest = _streaks([s["date"] for s in sessions])

    suggested = "focus meditation"
    recent = moods_collection.find_one({"user_id": owner}, sort=[("created_at", -1)])
    if recent:
        mood = (recent.get("mood") or "").lower()
        if mood in {"sad", "anxious", "stressed", "angry", "overwhelmed", "negative"}:
            suggested = "breathing / calming"
        elif mood in {"happy", "excited", "grateful", "positive"}:
            suggested = "gratitude meditation"

    return {
        "success": True,
        "current_streak": current,
        "longest_streak": longest,
        "total_sessions": len(sessions),
        "suggested_session": suggested,
    }


# ------------------------------------------------------------------ sleep
@app.post("/sleep")
def record_sleep(payload: SleepIn, current_user: str = Depends(get_current_user)):
    result = sleep_collection.insert_one(
        {
            "user_id": current_user,
            "bed_time": payload.bed_time,
            "wake_time": payload.wake_time,
            "quality": payload.quality,
            "created_at": utcnow(),
        }
    )
    return {"success": True, "sleep_id": str(result.inserted_id)}


@app.get("/sleep/{user_id}")
def get_sleep(owner: str = Depends(require_owner)):
    docs = list(sleep_collection.find({"user_id": owner}).sort("created_at", -1))
    return {"success": True, "sleep_records": _serialise(docs)}


# -------------------------------------------------------------- community
@app.post("/community/posts")
def create_post(payload: PostIn, current_user: str = Depends(get_current_user)):
    # A public wall inside a mental health app is exactly where a crisis
    # post lands. Route it the same way the chat does.
    assessment = safety.assess_risk(payload.content)
    if assessment.blocks_llm:
        safety.log_safety_event(
            safety_events_collection,
            user_id=current_user,
            session_id=None,
            assessment=assessment,
            action="community_post_intercepted",
            text_length=len(payload.content),
        )
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=safety.crisis_response(settings.CRISIS_REGION),
        )

    result = community_collection.insert_one(
        {
            "user_id": current_user,
            "content": payload.content,
            "likes": [],
            "created_at": utcnow(),
        }
    )
    return {"success": True, "post_id": str(result.inserted_id)}


@app.get("/community/posts")
def get_posts(current_user: str = Depends(get_current_user)):
    posts = list(community_collection.find().sort("created_at", -1).limit(50))
    for post in posts:
        post["_id"] = str(post["_id"])
        post["like_count"] = len(post.get("likes", []))
        post["liked_by_me"] = current_user in post.get("likes", [])
        # Never ship the full like roster — it leaks who else uses the app.
        post.pop("likes", None)
        # Pseudonymise authors; the wall is meant to be anonymous.
        post["author"] = (
            "You" if post["user_id"] == current_user else f"Member {abs(hash(post['user_id'])) % 9000 + 1000}"
        )
        post.pop("user_id", None)
    return {"success": True, "posts": posts}


@app.post("/community/posts/{post_id}/like")
def like_post(post_id: str, current_user: str = Depends(get_current_user)):
    post = community_collection.find_one({"_id": _oid(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    operator = "$pull" if current_user in post.get("likes", []) else "$addToSet"
    community_collection.update_one(
        {"_id": _oid(post_id)}, {operator: {"likes": current_user}}
    )
    return {"success": True}


# ------------------------------------------------------------------ goals
@app.post("/goals")
def create_goal(payload: GoalIn, current_user: str = Depends(get_current_user)):
    result = goals_collection.insert_one(
        {
            "user_id": current_user,
            "title": payload.title,
            "category": payload.category,
            "completed": False,
            "created_at": utcnow(),
        }
    )
    return {"success": True, "goal_id": str(result.inserted_id)}


@app.get("/goals/{user_id}")
def get_goals(owner: str = Depends(require_owner)):
    docs = list(goals_collection.find({"user_id": owner}).sort("created_at", -1))
    return {"success": True, "goals": _serialise(docs)}


@app.put("/goals/{goal_id}")
def update_goal(
    goal_id: str,
    payload: GoalUpdateIn,
    current_user: str = Depends(get_current_user),
):
    result = goals_collection.update_one(
        {"_id": _oid(goal_id), "user_id": current_user},
        {"$set": {"completed": payload.completed, "updated_at": utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"success": True}


@app.delete("/goals/{goal_id}")
def delete_goal(goal_id: str, current_user: str = Depends(get_current_user)):
    result = goals_collection.delete_one(
        {"_id": _oid(goal_id), "user_id": current_user}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"success": True}


# --------------------------------------------------------------- privacy
@app.get("/me/export")
def export_my_data(current_user: str = Depends(get_current_user)):
    """Data portability. For an app holding mental health records this is
    not a nice-to-have — it's the DPDP Act / GDPR baseline."""
    def dump(collection):
        return _serialise(list(collection.find({"user_id": current_user})))

    return {
        "user_id": current_user,
        "exported_at": utcnow().isoformat(),
        "messages": dump(messages_collection),
        "journals": dump(journals_collection),
        "moods": dump(moods_collection),
        "tasks": dump(tasks_collection),
        "goals": dump(goals_collection),
        "sleep": dump(sleep_collection),
        "meditation": dump(meditation_collection),
        "fitness_profile": dump(fitness_profiles_collection),
        "fitness_metrics": dump(fitness_metrics_collection),
        "fitness_plans": dump(fitness_plans_collection),
        "fitness_workouts": dump(fitness_workouts_collection),
    }


@app.delete("/me", response_model=OkOut)
def delete_my_account(current_user: str = Depends(get_current_user)) -> OkOut:
    for collection in (
        messages_collection,
        journals_collection,
        moods_collection,
        tasks_collection,
        goals_collection,
        sleep_collection,
        meditation_collection,
        sessions_collection,
        community_collection,
        fitness_profiles_collection,
        fitness_metrics_collection,
        fitness_plans_collection,
        fitness_workouts_collection,
    ):
        collection.delete_many({"user_id": current_user})
    users_collection.delete_one({"username": current_user})
    return OkOut()
