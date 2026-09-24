"""Personal Health Twin API.

    GET  /twin/overview/{user_id}          score, trend, insights, warning, today's plan
    POST /twin/actions/{action_id}/toggle  tick / untick one of today's actions
    POST /twin/report                      generate this week's report (AI + fallback)
    GET  /twin/report/{user_id}            latest weekly report

Reads only what the user already logs. Journal *text* and chat *text* are
never loaded – only dates, moods and sentiment labels – so the weekly AI
report is written from aggregate numbers, not from anyone's private words.
"""

from __future__ import annotations

import logging
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

import fitness_library
import llm
import safety
import twin_engine as engine
from auth import get_current_user, require_owner, utcnow
from config import settings
from db import (
    fitness_plans_collection,
    fitness_profiles_collection,
    fitness_workouts_collection,
    journals_collection,
    meditation_collection,
    messages_collection,
    moods_collection,
    safety_events_collection,
    sleep_collection,
    tasks_collection,
    twin_actions_collection,
    twin_reports_collection,
)
from ratelimit import limit
from schemas import TwinReportIn

log = logging.getLogger("twin")

router = APIRouter(prefix="/twin", tags=["health-twin"])

report_limit = limit("twin_report", 6, 300)

HISTORY_DAYS = 60
LANGUAGE_NAMES = {"en-US": "English", "hi-IN": "Hindi", "mr-IN": "Marathi"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ------------------------------------------------------------------ loading
def _load_raw(user_id: str, now) -> dict[str, list[dict]]:
    since = now - timedelta(days=HISTORY_DAYS + 1)
    recent = {"user_id": user_id, "created_at": {"$gte": since}}
    return {
        "moods": list(moods_collection.find(recent, {"mood": 1, "energy": 1, "created_at": 1})),
        # Journal content is deliberately NOT projected.
        "journals": list(journals_collection.find(recent, {"mood": 1, "created_at": 1})),
        "sleep": list(sleep_collection.find(
            recent, {"bed_time": 1, "wake_time": 1, "quality": 1, "created_at": 1})),
        "workouts": list(fitness_workouts_collection.find(
            recent, {"duration_min": 1, "intensity": 1, "created_at": 1})),
        "meditation": list(meditation_collection.find(
            {"user_id": user_id, "date": {"$gte": since.strftime("%Y-%m-%d")}},
            {"date": 1, "created_at": 1})),
        # Chat text is NOT projected – only the sentiment label.
        "messages": list(messages_collection.find(
            {"user_id": user_id, "sender": "user", "timestamp": {"$gte": since}},
            {"sender": 1, "sentiment": 1, "timestamp": 1})),
        "tasks": list(tasks_collection.find(
            {"user_id": user_id, "completed": True, "updated_at": {"$gte": since}},
            {"completed": 1, "updated_at": 1, "created_at": 1})),
    }


def _fitness_today(user_id: str, weekday: str) -> dict | None:
    doc = fitness_plans_collection.find_one(
        {"user_id": user_id}, {"plan.workout.schedule": 1}, sort=[("created_at", -1)]
    )
    try:
        for day in doc["plan"]["workout"]["schedule"]:
            if day.get("day") == weekday:
                return day
    except (TypeError, KeyError):
        pass
    return None


def _support(user_id: str, now) -> dict | None:
    """If the safety layer escalated recently, surface support gently.
    Never part of the score, never mentioned in the AI report."""
    try:
        count = safety_events_collection.count_documents(
            {"user_id": user_id, "tier": {"$gte": 2}, "created_at": {"$gte": now - timedelta(days=14)}}
        )
    except Exception:  # pragma: no cover
        count = 0
    if not count:
        return None
    return {
        "message": "Some of your recent conversations sounded really hard. You don't have to carry that alone – these lines are free and open now.",
        "resources": safety.format_resources(settings.CRISIS_REGION),
    }


def analyse(user_id: str, now=None) -> dict:
    now = now or utcnow()
    offset = settings.TZ_OFFSET_MINUTES
    today = engine.local_date(now, offset)
    days = engine.build_days(_load_raw(user_id, now), today, HISTORY_DAYS, offset)

    has_profile = fitness_profiles_collection.find_one({"user_id": user_id}, {"_id": 1}) is not None
    tracks = engine.tracking(days, has_profile)

    components = engine.score_components(days, len(days) - 1, tracks)
    score = engine.combine(components)
    week_ago = engine.combine(engine.score_components(days, len(days) - 8, tracks))
    delta = None if score is None or week_ago is None else score - week_ago

    found = engine.insights(days)
    warning = engine.early_warning(days, tracks)
    weekday = WEEKDAYS[today.weekday()]
    plan = engine.daily_plan(days, tracks, warning, found, _fitness_today(user_id, weekday))

    done = {
        d["action_id"]
        for d in twin_actions_collection.find(
            {"user_id": user_id, "date": today.isoformat()}, {"action_id": 1}
        )
    }
    for action in plan:
        action["done"] = action["id"] in done

    return {
        "date": today.isoformat(),
        "weekday": weekday,
        "score": score,
        **engine.score_label(score),
        "delta": delta,
        "components": [
            {
                "key": k,
                "label": engine.COMPONENT_LABELS[k],
                "value": v,
                "weight": engine.WEIGHTS[k],
                "tracked": v is not None,
            }
            for k, v in components.items()
        ],
        "trend": engine.score_series(days, tracks, 30),
        "insights": found,
        "insight_progress": engine.insight_progress(days),
        "warning": warning,
        "plan": plan,
        "snapshot": engine.snapshot(days),
        "tracking": tracks,
        "summary": engine.template_summary(score, delta, components, warning),
        "support": _support(user_id, now),
        "_days": days,  # stripped before returning to the client
    }


def _iso(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _public(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


# ---------------------------------------------------------------- routes
@router.get("/overview/{user_id}")
def overview(owner: str = Depends(require_owner)):
    return {"success": True, **_public(analyse(owner))}


@router.post("/actions/{action_id}/toggle")
def toggle_action(action_id: str, current_user: str = Depends(get_current_user)):
    if len(action_id) > 40:
        raise HTTPException(status_code=400, detail="Invalid action")
    today = engine.local_date(utcnow(), settings.TZ_OFFSET_MINUTES).isoformat()
    key = {"user_id": current_user, "date": today, "action_id": action_id}
    if twin_actions_collection.find_one(key):
        twin_actions_collection.delete_one(key)
        return {"success": True, "done": False}
    twin_actions_collection.insert_one({**key, "created_at": utcnow()})
    return {"success": True, "done": True}


def _template_report(result: dict, compare: list[dict]) -> tuple[str, str]:
    wins = [r for r in compare if r["trend"] == "up"]
    slips = [r for r in compare if r["trend"] == "down"]
    parts = []
    if result["score"] is not None:
        parts.append(f"This week your wellness score landed at {result['score']} ({result['label'].lower()}).")
    if wins:
        parts.append("Good news: " + ", ".join(w["label"].lower() for w in wins[:3]) + " improved on last week.")
    if slips:
        parts.append("A few things slipped – " + ", ".join(s["label"].lower() for s in slips[:3]) + ".")
    if result["insights"]:
        parts.append(f"Your clearest pattern so far: {result['insights'][0]['statement'].lower()}.")
    if not parts:
        parts.append("There isn't much data from this week yet – a few daily check-ins will make next week's report far more useful.")

    tracked = [c for c in result["components"] if c["tracked"] and c["key"] != "consistency"]
    focus = "Log your mood each day so your twin can learn what helps you."
    if tracked:
        weakest = min(tracked, key=lambda c: c["value"])
        focus = {
            "mood": "Plan one thing each day that reliably lifts your mood – and log how it went.",
            "sleep": "Protect your sleep: aim for a consistent bedtime and 7+ hours on most nights.",
            "activity": "Build toward 150 active minutes – even three 20-minute walks move the needle.",
            "mindfulness": "Add two short meditation or journaling sessions this week.",
        }.get(weakest["key"], focus)
    return " ".join(parts), focus


@router.post("/report", dependencies=[Depends(report_limit)])
def weekly_report(payload: TwinReportIn, current_user: str = Depends(get_current_user)):
    now = utcnow()
    result = analyse(current_user, now)
    today = engine.local_date(now, settings.TZ_OFFSET_MINUTES)
    week_start = (today - timedelta(days=today.weekday())).isoformat()

    if not payload.refresh:
        cached = twin_reports_collection.find_one(
            {"user_id": current_user, "week_start": week_start, "language": payload.language},
            {"_id": 0, "user_id": 0},
            sort=[("created_at", -1)],
        )
        if cached:
            cached["created_at"] = _iso(cached["created_at"])
            return {"success": True, **cached}

    compare = engine.week_compare(result["_days"])
    narrative, focus = _template_report(result, compare)
    source = "template"

    language = LANGUAGE_NAMES.get(payload.language, "English")
    facts = {
        "wellness_score": result["score"],
        "score_label": result["label"],
        "change_vs_last_week": result["delta"],
        "components": {c["label"]: c["value"] for c in result["components"] if c["tracked"]},
        "this_week_vs_last": [
            {k: r[k] for k in ("label", "this_week", "last_week", "unit", "trend")} for r in compare
        ],
        "personal_patterns": [i["statement"] for i in result["insights"]],
        "early_warning": result["warning"]["level"],
    }
    try:
        raw = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are MindWell's Personal Health Twin writing a weekly check-in for the user. "
                        "Write in second person, warm and specific, 110–160 words. Use the numbers you are given; "
                        "do not invent any. Personal patterns are correlations, not proof – say 'linked with', "
                        "never 'causes'. No diagnosis, no medical claims, no weight or calorie talk. Celebrate what "
                        "improved, be gentle about what slipped. "
                        f"Write in {language}. Return ONLY JSON: "
                        '{"narrative": "...", "focus": "one concrete focus for next week, one sentence"}'
                    ),
                },
                {"role": "user", "content": str(facts)},
            ],
            temperature=0.6,
            max_tokens=500,
        )
        parsed = fitness_library.extract_json(raw) or {}
        if isinstance(parsed.get("narrative"), str) and len(parsed["narrative"]) > 40:
            narrative = parsed["narrative"].strip()[:1500]
            if isinstance(parsed.get("focus"), str) and parsed["focus"].strip():
                focus = parsed["focus"].strip()[:300]
            source = "ai"
    except llm.LLMUnavailable:
        pass

    doc = {
        "user_id": current_user,
        "week_start": week_start,
        "language": payload.language,
        "score": result["score"],
        "label": result["label"],
        "delta": result["delta"],
        "compare": compare,
        "wins": [r["label"] for r in compare if r["trend"] == "up"],
        "slips": [r["label"] for r in compare if r["trend"] == "down"],
        "narrative": narrative,
        "focus": focus,
        "source": source,
        "created_at": now,
    }
    twin_reports_collection.insert_one(dict(doc))
    doc.pop("user_id")
    doc["created_at"] = _iso(now)
    return {"success": True, **doc}


@router.get("/report/{user_id}")
def latest_report(owner: str = Depends(require_owner)):
    doc = twin_reports_collection.find_one(
        {"user_id": owner}, {"_id": 0, "user_id": 0}, sort=[("created_at", -1)]
    )
    if not doc:
        return {"success": True, "report": None}
    doc["created_at"] = _iso(doc["created_at"])
    return {"success": True, "report": doc}
