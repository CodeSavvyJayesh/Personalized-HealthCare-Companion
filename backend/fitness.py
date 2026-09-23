"""Physical fitness API.

    GET    /fitness/profile/{user_id}   profile, computed metrics, weight history
    PUT    /fitness/profile             create/update profile, returns metrics
    POST   /fitness/weight              quick weigh-in
    POST   /fitness/plan                generate an AI workout + diet plan
    GET    /fitness/plan/{user_id}      latest plan
    POST   /fitness/workouts            log a completed session
    GET    /fitness/workouts/{user_id}  history + weekly stats
    DELETE /fitness/workouts/{id}       remove a log entry
    POST   /fitness/coach               ask the AI coach a question

Numbers come from `fitness_calc` (deterministic, tested). The LLM writes
the plan around them, and `fitness_library.normalise_plan` validates what
it returns. If the model is down, the rule-based plan is served instead and
the response says so – the feature degrades, it doesn't disappear.

Free text (injuries, notes, coach questions) goes through the same crisis
classifier as the chat. This is still a mental health app, and a fitness
screen is a place where eating-disorder and self-harm language can show up.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

import fitness_calc as calc
import fitness_library as library
import llm
import safety
from auth import get_current_user, require_owner, utcnow
from config import settings
from db import (
    fitness_metrics_collection,
    fitness_plans_collection,
    fitness_profiles_collection,
    fitness_workouts_collection,
    moods_collection,
    safety_events_collection,
    sleep_collection,
)
from ratelimit import limit
from schemas import (
    CoachIn,
    FitnessPlanIn,
    FitnessProfileIn,
    WeightIn,
    WorkoutLogIn,
)

log = logging.getLogger("fitness")

router = APIRouter(prefix="/fitness", tags=["fitness"])

plan_limit = limit("fitness_plan", 6, 300)
coach_limit = limit("fitness_coach", 20, 60)

LANGUAGE_NAMES = {"en-US": "English", "hi-IN": "Hindi", "mr-IN": "Marathi"}

# Requests for severe restriction are answered with fixed, reviewed text and
# never reach the model – the same idea as Tier 3 in the safety layer.
_RESTRICTION = re.compile(
    r"\b("
    r"stop eating|not eat(ing)? (at all|anything|for \d+ days)|starv(e|ing)|"
    r"eat nothing|skip (all|every) meals?|"
    r"(make|made) (myself|me) (throw up|vomit|puke)|purg(e|ing)|laxatives? to lose|"
    r"([1-7]\d{2}|[1-9]\d?) ?(k?cal|calories) (a|per) day|"
    r"lose \d{2,} ?(kg|kilos?) in (a|one|1|2|two) (week|weeks)|"
    r"water fast|dry fast"
    r")\b",
    re.IGNORECASE,
)


def _restriction_response() -> str:
    return (
        "I can't help with eating that little or with ways to lose weight "
        "that fast – it would put real strain on your heart, mood and "
        "energy, and I care more about you feeling well than about a number "
        "on the scale.\n\n"
        "What I **can** do is help you build a plan that fuels you properly "
        "while you get stronger. Your plan's calorie target already has a "
        "safe minimum built in.\n\n"
        "If thoughts about food, eating or your body have been taking up a "
        "lot of space lately, that's worth talking about with someone – a "
        "doctor, a counsellor, or someone you trust. You can also talk to "
        "the MindWell companion in the **Therapist AI** tab any time.\n\n"
        f"{safety.format_resources(settings.CRISIS_REGION)}"
    )


# ------------------------------------------------------------------ helpers
def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Malformed id")


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def _check_text(text: str, user_id: str, action: str) -> safety.RiskAssessment | None:
    """Run free text through the crisis classifier. Tier 3 is intercepted."""
    if not text or not text.strip():
        return None
    assessment = safety.assess_risk(text)
    if assessment.blocks_llm:
        safety.log_safety_event(
            safety_events_collection,
            user_id=user_id,
            session_id=None,
            assessment=assessment,
            action=action,
            text_length=len(text),
        )
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=safety.crisis_response(settings.CRISIS_REGION),
        )
    return assessment


def _profile_or_404(user_id: str) -> dict:
    profile = fitness_profiles_collection.find_one({"user_id": user_id}, {"_id": 0})
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Set up your fitness profile first.",
        )
    return profile


def _history(user_id: str, limit_n: int = 90) -> list[dict]:
    docs = list(
        fitness_metrics_collection.find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(limit_n)
    )
    docs.reverse()
    return [
        {
            "date": _iso(d["created_at"]),
            "weight_kg": d["weight_kg"],
            "bmi": d["bmi"],
        }
        for d in docs
    ]


def _snapshot(user_id: str, profile: dict, metrics: dict) -> None:
    fitness_metrics_collection.insert_one(
        {
            "user_id": user_id,
            "weight_kg": profile["weight_kg"],
            "height_cm": profile["height_cm"],
            "bmi": metrics["bmi"],
            "bmi_category": metrics["bmi_category"],
            "created_at": utcnow(),
        }
    )


def _sleep_hours(bed: str, wake: str) -> float | None:
    try:
        bh, bm = (int(x) for x in bed.split(":"))
        wh, wm = (int(x) for x in wake.split(":"))
    except (ValueError, AttributeError):
        return None
    minutes = (wh * 60 + wm) - (bh * 60 + bm)
    if minutes <= 0:
        minutes += 24 * 60
    return minutes / 60


def _wellbeing_context(user_id: str) -> dict:
    """Recent energy and sleep, so a plan generated on a rough week is
    gentler. Read-only and best-effort."""
    ctx = {"low_energy": False, "short_sleep": False}
    since = utcnow() - timedelta(days=3)
    try:
        mood = moods_collection.find_one(
            {"user_id": user_id, "created_at": {"$gte": since}},
            sort=[("created_at", -1)],
        )
        if mood and isinstance(mood.get("energy"), (int, float)) and mood["energy"] <= 3:
            ctx["low_energy"] = True
        sleep = sleep_collection.find_one(
            {"user_id": user_id, "created_at": {"$gte": since}},
            sort=[("created_at", -1)],
        )
        if sleep:
            hours = _sleep_hours(sleep.get("bed_time", ""), sleep.get("wake_time", ""))
            if hours is not None and hours < 6:
                ctx["short_sleep"] = True
    except Exception as exc:  # pragma: no cover - context is optional
        log.warning("Could not read wellbeing context: %s", exc)
    return ctx


# ------------------------------------------------------------------ profile
@router.get("/profile/{user_id}")
def get_profile(owner: str = Depends(require_owner)):
    profile = fitness_profiles_collection.find_one({"user_id": owner}, {"_id": 0})
    if not profile:
        return {"success": True, "profile": None, "metrics": None, "history": []}
    profile["updated_at"] = _iso(profile.get("updated_at"))
    return {
        "success": True,
        "profile": profile,
        "metrics": calc.compute_metrics(profile),
        "history": _history(owner),
    }


@router.put("/profile")
def save_profile(payload: FitnessProfileIn, current_user: str = Depends(get_current_user)):
    _check_text(payload.injuries, current_user, "fitness_profile_intercepted")

    data = payload.model_dump()
    data["height_cm"] = round(data["height_cm"], 1)
    data["weight_kg"] = round(data["weight_kg"], 1)
    previous = fitness_profiles_collection.find_one({"user_id": current_user})

    fitness_profiles_collection.update_one(
        {"user_id": current_user},
        {
            "$set": {**data, "user_id": current_user, "updated_at": utcnow()},
            "$setOnInsert": {"created_at": utcnow()},
        },
        upsert=True,
    )
    metrics = calc.compute_metrics(data)

    # Only add a history point when the body numbers actually changed.
    if (
        not previous
        or previous.get("weight_kg") != data["weight_kg"]
        or previous.get("height_cm") != data["height_cm"]
    ):
        _snapshot(current_user, data, metrics)

    return {
        "success": True,
        "profile": data,
        "metrics": metrics,
        "history": _history(current_user),
    }


@router.post("/weight")
def log_weight(payload: WeightIn, current_user: str = Depends(get_current_user)):
    profile = _profile_or_404(current_user)
    profile["weight_kg"] = round(payload.weight_kg, 1)
    fitness_profiles_collection.update_one(
        {"user_id": current_user},
        {"$set": {"weight_kg": profile["weight_kg"], "updated_at": utcnow()}},
    )
    metrics = calc.compute_metrics(profile)
    _snapshot(current_user, profile, metrics)
    return {"success": True, "metrics": metrics, "history": _history(current_user)}


# --------------------------------------------------------------------- plan
@router.post("/plan", dependencies=[Depends(plan_limit)])
def generate_plan(payload: FitnessPlanIn, current_user: str = Depends(get_current_user)):
    profile = _profile_or_404(current_user)
    metrics = calc.compute_metrics(profile)
    context = _wellbeing_context(current_user)
    context["language_name"] = LANGUAGE_NAMES.get(payload.language, "English")

    fallback = library.rule_based_plan(profile, metrics, context)
    source = "ai"
    patched: list[str] = []
    try:
        raw = llm.chat(
            library.ai_messages(profile, metrics, context),
            temperature=0.6,
            max_tokens=3500,
            timeout=max(settings.LLM_TIMEOUT, 150),
        )
        plan, patched = library.normalise_plan(
            library.extract_json(raw), fallback, profile, metrics
        )
        if patched == ["all"]:
            source = "rule_based"
            patched = []
            log.warning("LLM returned an unparseable plan; using rule-based plan")
    except llm.LLMUnavailable:
        plan, source = fallback, "rule_based"

    # Guardrails always come from the calculator, never the model.
    plan["guardrails"] = metrics["guardrails"]
    plan["context"] = {k: v for k, v in context.items() if k != "language_name"}

    doc = {
        "user_id": current_user,
        "plan": plan,
        "source": source,
        "patched": patched,
        "metrics": metrics,
        "profile": {k: v for k, v in profile.items() if k not in {"user_id", "created_at", "updated_at"}},
        "created_at": utcnow(),
    }
    result = fitness_plans_collection.insert_one(doc)
    return {
        "success": True,
        "plan_id": str(result.inserted_id),
        "plan": plan,
        "source": source,
        "patched": patched,
        "metrics": metrics,
        "created_at": _iso(doc["created_at"]),
    }


@router.get("/plan/{user_id}")
def latest_plan(owner: str = Depends(require_owner)):
    doc = fitness_plans_collection.find_one({"user_id": owner}, sort=[("created_at", -1)])
    if not doc:
        return {"success": True, "plan": None}
    return {
        "success": True,
        "plan_id": str(doc["_id"]),
        "plan": doc["plan"],
        "source": doc.get("source", "ai"),
        "patched": doc.get("patched", []),
        "metrics": doc.get("metrics"),
        "created_at": _iso(doc["created_at"]),
    }


# ----------------------------------------------------------------- workouts
@router.post("/workouts")
def log_workout(payload: WorkoutLogIn, current_user: str = Depends(get_current_user)):
    _check_text(payload.notes, current_user, "fitness_note_intercepted")
    profile = fitness_profiles_collection.find_one({"user_id": current_user}) or {}
    weight = float(profile.get("weight_kg") or 65)
    doc = {
        "user_id": current_user,
        **payload.model_dump(),
        "calories": calc.calories_burned(
            payload.category, payload.intensity, payload.duration_min, weight
        ),
        "created_at": utcnow(),
    }
    result = fitness_workouts_collection.insert_one(doc)
    return {"success": True, "workout_id": str(result.inserted_id), "calories": doc["calories"]}


def workout_stats(docs: list[dict], now: datetime) -> dict:
    """Weekly totals, WHO-minutes progress, streak and an 8-week series."""
    today = now.date()
    week_start = today - timedelta(days=today.weekday())

    week = [d for d in docs if d["created_at"].date() >= week_start]
    credit = sum(calc.activity_minutes_credit(d["intensity"], d["duration_min"]) for d in week)

    days = {d["created_at"].date() for d in docs}
    streak = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)

    series = []
    for i in range(7, -1, -1):
        start = week_start - timedelta(weeks=i)
        end = start + timedelta(days=7)
        in_week = [d for d in docs if start <= d["created_at"].date() < end]
        series.append(
            {
                "week": start.strftime("%d %b"),
                "minutes": sum(d["duration_min"] for d in in_week),
                "sessions": len(in_week),
            }
        )

    return {
        "week_minutes": sum(d["duration_min"] for d in week),
        "week_active_minutes": credit,
        "who_target": 150,
        "week_sessions": len(week),
        "week_calories": sum(d.get("calories", 0) for d in week),
        "total_sessions": len(docs),
        "streak_days": streak,
        "weekly": series,
    }


@router.get("/workouts/{user_id}")
def get_workouts(owner: str = Depends(require_owner)):
    since = utcnow() - timedelta(weeks=9)
    recent = list(
        fitness_workouts_collection.find({"user_id": owner, "created_at": {"$gte": since}})
        .sort("created_at", -1)
    )
    for d in recent:
        if d["created_at"].tzinfo is None:
            d["created_at"] = d["created_at"].replace(tzinfo=timezone.utc)
    stats = workout_stats(recent, utcnow())
    items = [
        {
            "_id": str(d["_id"]),
            "activity": d["activity"],
            "category": d["category"],
            "duration_min": d["duration_min"],
            "intensity": d["intensity"],
            "notes": d.get("notes", ""),
            "plan_day": d.get("plan_day"),
            "calories": d.get("calories", 0),
            "created_at": _iso(d["created_at"]),
        }
        for d in recent[:50]
    ]
    return {"success": True, "workouts": items, "stats": stats}


@router.delete("/workouts/{workout_id}")
def delete_workout(workout_id: str, current_user: str = Depends(get_current_user)):
    result = fitness_workouts_collection.delete_one(
        {"_id": _oid(workout_id), "user_id": current_user}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workout not found")
    return {"success": True}


# -------------------------------------------------------------------- coach
@router.post("/coach", dependencies=[Depends(coach_limit)])
def ask_coach(payload: CoachIn, current_user: str = Depends(get_current_user)):
    assessment = safety.assess_risk(payload.question)
    if assessment.blocks_llm:
        safety.log_safety_event(
            safety_events_collection,
            user_id=current_user,
            session_id=None,
            assessment=assessment,
            action="fitness_coach_intercepted",
            text_length=len(payload.question),
        )
        return {
            "success": True,
            "answer": safety.crisis_response(settings.CRISIS_REGION),
            "source": "safety",
            "resources_shown": True,
        }

    if _RESTRICTION.search(payload.question):
        return {
            "success": True,
            "answer": _restriction_response(),
            "source": "safety",
            "resources_shown": True,
        }

    profile = fitness_profiles_collection.find_one({"user_id": current_user}, {"_id": 0})
    about = "The user has not set up a fitness profile yet."
    if profile:
        m = calc.compute_metrics(profile)
        about = (
            f"User: {profile['age']} y, {profile['sex']}, {profile['height_cm']} cm, "
            f"{profile['weight_kg']} kg, BMI {m['bmi']} ({m['bmi_category']}). "
            f"Goal: {m['goal_label']}. Experience: {profile['experience']}. "
            f"Equipment: {profile['equipment']}. Diet: {profile['diet_preference']}. "
            f"Daily target {m['target_calories']} kcal, protein {m['macros']['protein_g']} g. "
            f"Injuries/limitations: {profile.get('injuries') or 'none'}."
        )

    language = LANGUAGE_NAMES.get(payload.language, "English")
    system = (
        "You are MindWell's fitness and nutrition coach inside a mental-wellbeing app. "
        "Answer in clear Markdown, under 220 words, practical and specific to the user. "
        "Never recommend crash diets, fasting protocols, intakes below 1200 kcal, fat burners, "
        "steroids or unregulated supplements. Never comment on appearance. "
        "For pain, dizziness, chest symptoms or medical conditions, advise seeing a doctor. "
        "If a question is outside fitness, nutrition, sleep or movement, gently steer back. "
        f"Reply in {language}.\n\n{about}"
    )
    if assessment.needs_resources:
        system += "\n\n" + safety.SAFE_MODE_PROMPT

    try:
        answer = llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": payload.question},
            ],
            temperature=0.6,
            max_tokens=600,
        )
        source = "ai"
    except llm.LLMUnavailable:
        answer = (
            "The AI coach is offline right now, so here are the basics that "
            "apply to almost everyone:\n\n"
            "- **Move most days** – 150 minutes of moderate activity a week, plus 2 strength sessions.\n"
            "- **Protein at every meal** – dal, paneer, curd, eggs or tofu.\n"
            "- **Sleep 7–9 hours** – it drives recovery and appetite control.\n"
            "- **Progress slowly** – add a little weight or a few reps each week.\n\n"
            "Your personalised plan in the **My AI Plan** tab still works without the AI."
        )
        source = "fallback"

    if assessment.needs_resources:
        answer = safety.append_resources(answer, settings.CRISIS_REGION)
    return {
        "success": True,
        "answer": answer,
        "source": source,
        "resources_shown": assessment.needs_resources,
    }
