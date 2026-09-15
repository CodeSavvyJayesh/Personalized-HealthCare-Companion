"""Insights / analytics.

Changes from the original:

* Authenticated and owner-scoped (`require_owner`).
* NEUTRAL is a real bucket now, so the pie chart stops lying.
* Only the *user's own* messages count toward their mood. Previously the
  bot's replies were counted too, which meant the dashboard was partly
  measuring the chatbot's tone, not the person's.
* Sentiment weighted by model confidence instead of a flat ±1.
* The seven-day trend distinguishes "no data" from "neutral day" — those
  are not the same thing and drawing them identically is misleading.
* LLM failure falls back to rules; the LLM is an enhancement, not a
  dependency.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends

import llm
from auth import require_owner, utcnow
from db import (
    goals_collection,
    journals_collection,
    meditation_collection,
    messages_collection,
    sleep_collection,
    tasks_collection,
)
from sentiment import polarity

log = logging.getLogger(__name__)
router = APIRouter(tags=["insights"])


def _parse_duration(bed: str, wake: str) -> float | None:
    try:
        b_h, b_m = map(int, bed.split(":"))
        w_h, w_m = map(int, wake.split(":"))
    except (ValueError, AttributeError):
        return None
    b = b_h * 60 + b_m
    w = w_h * 60 + w_m
    if w < b:
        w += 24 * 60
    return (w - b) / 60.0


def _streak(dates: list[str]) -> int:
    from datetime import datetime

    if not dates:
        return 0
    unique = sorted(set(dates))
    run = 1
    for i in range(1, len(unique)):
        prev = datetime.strptime(unique[i - 1], "%Y-%m-%d")
        curr = datetime.strptime(unique[i], "%Y-%m-%d")
        run = run + 1 if (curr - prev).days == 1 else 1
    last = datetime.strptime(unique[-1], "%Y-%m-%d").date()
    return run if (utcnow().date() - last) <= timedelta(days=1) else 0


@router.get("/insights/{user_id}")
def get_insights(owner: str = Depends(require_owner)) -> dict:
    # ---------------------------------------------------------- sentiment
    messages = list(
        messages_collection.find({"user_id": owner, "sender": "user"}).sort(
            "timestamp", 1
        )
    )

    counts = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}
    weighted_sum = 0.0
    current_streak = max_streak = 0
    seven_days_ago = utcnow() - timedelta(days=7)
    daily: dict[str, dict[str, float]] = {}

    for msg in messages:
        label = (msg.get("sentiment") or "NEUTRAL").upper()
        if label not in counts:
            label = "NEUTRAL"
        counts[label] += 1

        confidence = float(msg.get("sentiment_confidence") or 1.0)
        score = polarity(label) * confidence
        weighted_sum += score

        if label == "NEGATIVE":
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

        timestamp = msg.get("timestamp")
        if timestamp and timestamp >= seven_days_ago:
            key = timestamp.strftime("%Y-%m-%d")
            bucket = daily.setdefault(key, {"sum": 0.0, "count": 0})
            bucket["sum"] += score
            bucket["count"] += 1

    total = sum(counts.values())
    mood_score = 50
    if total:
        mood_score = max(0, min(100, int((weighted_sum / total + 1) * 50)))

    def pct(value: int) -> int:
        return int(round((value / total) * 100)) if total else 0

    mood_trend = []
    for offset in range(6, -1, -1):
        day = (utcnow() - timedelta(days=offset)).strftime("%Y-%m-%d")
        bucket = daily.get(day)
        if bucket and bucket["count"]:
            avg = bucket["sum"] / bucket["count"]
            mood_trend.append(
                {
                    "date": day,
                    "score": max(0, min(100, int((avg + 1) * 50))),
                    "has_data": True,
                    "entries": bucket["count"],
                }
            )
        else:
            # A day you didn't talk is not a neutral day.
            mood_trend.append(
                {"date": day, "score": None, "has_data": False, "entries": 0}
            )

    # -------------------------------------------------------------- sleep
    sleep_records = list(sleep_collection.find({"user_id": owner}))
    durations = [
        d
        for d in (
            _parse_duration(r.get("bed_time"), r.get("wake_time"))
            for r in sleep_records
        )
        if d is not None
    ]
    sleep_avg = round(sum(durations) / len(durations), 1) if durations else 0
    low_sleep_days = sum(1 for d in durations if d < 6)

    # --------------------------------------------------------- meditation
    meditation = list(meditation_collection.find({"user_id": owner}))
    med_dates = [m["date"] for m in meditation if m.get("date")]

    # ------------------------------------------------------- productivity
    tasks = list(tasks_collection.find({"user_id": owner}))
    goals = list(goals_collection.find({"user_id": owner}))
    completed_tasks = sum(1 for t in tasks if t.get("completed") is True)
    completed_goals = sum(1 for g in goals if g.get("completed") is True)

    def rate(done: int, all_: int) -> int:
        return int(round((done / all_) * 100)) if all_ else 0

    total_items = len(tasks) + len(goals)
    completed_items = completed_tasks + completed_goals

    total_journals = journals_collection.count_documents({"user_id": owner})

    stats = {
        "mood_score": mood_score,
        "pos_pct": pct(counts["POSITIVE"]),
        "neg_pct": pct(counts["NEGATIVE"]),
        "neu_pct": pct(counts["NEUTRAL"]),
        "stress_streak": max_streak,
        "sleep_avg": sleep_avg,
        "meditation_sessions": len(meditation),
        "task_rate": rate(completed_tasks, len(tasks)),
    }

    insights, suggestions = _generate_narrative(stats)

    return {
        "mood_score": mood_score,
        "sentiment": {
            "positive": stats["pos_pct"],
            "negative": stats["neg_pct"],
            "neutral": stats["neu_pct"],
        },
        "sentiment_counts": counts,
        "stress_streak": max_streak,
        "sleep": {"average": sleep_avg, "low_sleep_days": low_sleep_days},
        "meditation": {
            "total_sessions": len(meditation),
            "streak": _streak(med_dates),
        },
        "productivity": {
            "task_completion_rate": rate(completed_tasks, len(tasks)),
            "goal_completion_rate": rate(completed_goals, len(goals)),
            "overall_productivity": rate(completed_items, total_items),
            "total_tasks": len(tasks),
            "total_goals": len(goals),
            "completed_tasks": completed_tasks,
            "completed_goals": completed_goals,
        },
        "journals": {"total_entries": total_journals},
        "mood_trend": mood_trend,
        "insights": insights[:3],
        "suggestions": suggestions[:3],
        "data_points": total,
    }


def _rule_based(stats: dict) -> tuple[list[str], list[str]]:
    insights: list[str] = []
    suggestions: list[str] = []

    if stats["neg_pct"] > stats["pos_pct"]:
        insights.append("Your messages have leaned more negative recently.")
        suggestions.append("Try a short break to breathe and reset before your next task.")
    elif stats["pos_pct"] > stats["neg_pct"]:
        insights.append("Your mood has been generally positive this week.")
        suggestions.append("Note down what's been working — it's easier to repeat than rediscover.")

    if 0 < stats["sleep_avg"] < 6:
        insights.append(
            f"You're averaging {stats['sleep_avg']} hours of sleep, which is below "
            "what most people need."
        )
        suggestions.append("Aim for a fixed wind-down time tonight, even by 30 minutes.")

    if stats["meditation_sessions"] > 3:
        insights.append("Your meditation habit is becoming consistent.")
        suggestions.append("Keep the streak going — consistency matters more than length.")

    if stats["stress_streak"] >= 3:
        insights.append("You had several difficult moments close together.")
        suggestions.append("Journaling can help you unpack a stretch like that.")

    if not insights:
        insights.append("You're still building a baseline — keep checking in.")
    if not suggestions:
        suggestions.append("Log a mood or a journal entry to unlock sharper insights.")

    return insights, suggestions


def _generate_narrative(stats: dict) -> tuple[list[str], list[str]]:
    prompt = f"""You are a mental wellness analytics assistant.

User data:
- Mood score: {stats['mood_score']}/100
- Positive: {stats['pos_pct']}%  Negative: {stats['neg_pct']}%  Neutral: {stats['neu_pct']}%
- Longest run of negative messages: {stats['stress_streak']}
- Average sleep: {stats['sleep_avg']} hours
- Meditation sessions: {stats['meditation_sessions']}
- Task completion: {stats['task_rate']}%

Write exactly 3 insights and exactly 3 suggestions. Supportive, specific,
no diagnosis, no medical advice. Format:

Insights:
- ...
Suggestions:
- ..."""

    try:
        reply = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
            timeout=20,
        )
    except llm.LLMUnavailable as exc:
        log.info("Insights falling back to rules: %s", exc)
        return _rule_based(stats)

    insights: list[str] = []
    suggestions: list[str] = []
    section = None
    for raw in reply.splitlines():
        line = raw.strip()
        lowered = line.lower()
        if lowered.startswith("insight"):
            section = "insights"
            continue
        if lowered.startswith("suggestion"):
            section = "suggestions"
            continue
        if not line:
            continue
        if line[0] in "-*•" or (len(line) > 2 and line[0].isdigit() and line[1] in ".)"):
            cleaned = line.lstrip("-*•0123456789.) ").strip()
            if cleaned and section == "insights":
                insights.append(cleaned)
            elif cleaned and section == "suggestions":
                suggestions.append(cleaned)

    if not insights or not suggestions:
        fallback_i, fallback_s = _rule_based(stats)
        insights = insights or fallback_i
        suggestions = suggestions or fallback_s

    return insights, suggestions
