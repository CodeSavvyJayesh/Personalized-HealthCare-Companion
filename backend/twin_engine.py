"""Personal Health Twin – the analysis engine.

Turns everything a user already logs (mood, sleep, workouts, meditation,
journals, chat sentiment, tasks) into:

* a per-day feature table,
* a 0–100 Wellness Score with a component breakdown,
* personal "what affects you" insights (effect sizes, not vibes),
* an early-warning check against the user's own baseline,
* today's plan – three actions chosen from their current state.

Pure functions, no database and no model, so every number is reproducible
and unit-tested. The LLM (in `twin.py`) only writes prose around these
results, the same principle as the crisis layer and the fitness module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any, Callable, Iterable

# ------------------------------------------------------------------ mapping
# Mood Tracker ids (1–5) and Journal mood ids share one scale.
MOOD_SCORES = {
    "happy": 5, "grateful": 5, "excited": 5,
    "calm": 4, "content": 4,
    "neutral": 3, "okay": 3,
    "tired": 2, "sad": 2,
    "angry": 1.5, "stressed": 1.5,
    "anxious": 1,
}

SLEEP_QUALITY = {"excellent": 5, "good": 4, "fair": 3, "poor": 2, "bad": 1}
SENTIMENT_POINTS = {"POSITIVE": 100.0, "NEUTRAL": 50.0, "NEGATIVE": 0.0}

WEIGHTS = {"mood": 30, "sleep": 25, "activity": 20, "mindfulness": 10, "consistency": 15}

COMPONENT_LABELS = {
    "mood": "Mood",
    "sleep": "Sleep",
    "activity": "Activity",
    "mindfulness": "Mindfulness",
    "consistency": "Consistency",
}


def mood_points(mood: Any) -> float | None:
    """1–5 mood scale → 0–100."""
    score = MOOD_SCORES.get(str(mood or "").strip().lower())
    return None if score is None else (score - 1) / 4 * 100


def sleep_quality_value(q: Any) -> float | None:
    if q is None:
        return None
    if isinstance(q, (int, float)):
        return float(q) if 1 <= q <= 5 else None
    return SLEEP_QUALITY.get(str(q).strip().lower())


def sleep_hours(bed: str | None, wake: str | None) -> float | None:
    try:
        bh, bm = (int(x) for x in str(bed).split(":"))
        wh, wm = (int(x) for x in str(wake).split(":"))
    except (TypeError, ValueError):
        return None
    minutes = (wh * 60 + wm) - (bh * 60 + bm)
    if minutes <= 0:
        minutes += 24 * 60
    hours = minutes / 60
    return round(hours, 2) if 1 <= hours <= 16 else None


def sleep_points(hours: float, quality: float | None = None) -> float:
    """Sleep-duration curve centred on the 7–9 h adult recommendation."""
    if 7 <= hours <= 9:
        pts = 100.0
    elif 6 <= hours < 7:
        pts = 60 + (hours - 6) * 40
    elif 9 < hours <= 10:
        pts = 100 - (hours - 9) * 25
    elif 5 <= hours < 6:
        pts = 35 + (hours - 5) * 25
    elif hours > 10:
        pts = 60.0
    else:
        pts = max(10.0, hours * 7)
    if quality is not None:
        pts = pts * 0.8 + (quality - 1) / 4 * 100 * 0.2
    return round(pts, 1)


# -------------------------------------------------------------------- days
@dataclass
class Day:
    date: date
    moods: list[float] = field(default_factory=list)
    energy: list[float] = field(default_factory=list)
    journal_moods: list[float] = field(default_factory=list)
    sleep_h: float | None = None          # the night *before* this day
    sleep_q: float | None = None
    active_min: int = 0
    active_credit: int = 0                # WHO credit: vigorous counts double
    workouts: int = 0
    meditated: bool = False
    journaled: bool = False
    chat: list[float] = field(default_factory=list)
    tasks_done: int = 0

    @property
    def mood(self) -> float | None:
        if self.moods:
            return mean(self.moods)
        if self.journal_moods:
            return mean(self.journal_moods)
        return None

    @property
    def energy_avg(self) -> float | None:
        return mean(self.energy) if self.energy else None

    @property
    def chat_score(self) -> float | None:
        return mean(self.chat) if self.chat else None

    @property
    def mindful(self) -> bool:
        return self.meditated or self.journaled

    @property
    def logged(self) -> bool:
        return bool(
            self.moods or self.journal_moods or self.sleep_h is not None
            or self.workouts or self.meditated or self.journaled or self.tasks_done
        )


def local_date(ts: Any, offset_minutes: int) -> date | None:
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(ts, datetime):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (ts.astimezone(timezone.utc) + timedelta(minutes=offset_minutes)).date()


def build_days(
    raw: dict[str, list[dict]],
    today: date,
    n_days: int,
    offset_minutes: int = 330,
) -> list[Day]:
    """Bucket raw documents into `n_days` consecutive local days ending today."""
    start = today - timedelta(days=n_days - 1)
    days = {start + timedelta(days=i): Day(start + timedelta(days=i)) for i in range(n_days)}

    def bucket(ts):
        d = local_date(ts, offset_minutes)
        return days.get(d) if d else None

    for m in raw.get("moods", []):
        day = bucket(m.get("created_at"))
        if not day:
            continue
        pts = mood_points(m.get("mood"))
        if pts is not None:
            day.moods.append(pts)
        if isinstance(m.get("energy"), (int, float)):
            day.energy.append(float(m["energy"]))

    for j in raw.get("journals", []):
        day = bucket(j.get("created_at"))
        if not day:
            continue
        day.journaled = True
        pts = mood_points(j.get("mood"))
        if pts is not None:
            day.journal_moods.append(pts)

    for s in raw.get("sleep", []):
        day = bucket(s.get("created_at"))
        hours = sleep_hours(s.get("bed_time"), s.get("wake_time"))
        if not day or hours is None:
            continue
        day.sleep_h = hours  # latest record of the day wins
        day.sleep_q = sleep_quality_value(s.get("quality"))

    for w in raw.get("workouts", []):
        day = bucket(w.get("created_at"))
        if not day:
            continue
        minutes = int(w.get("duration_min") or 0)
        day.workouts += 1
        day.active_min += minutes
        day.active_credit += minutes * 2 if w.get("intensity") == "high" else minutes

    for m in raw.get("meditation", []):
        day = bucket(m.get("created_at"))
        if day is None and m.get("date"):
            try:
                day = days.get(date.fromisoformat(m["date"]))
            except ValueError:
                day = None
        if day:
            day.meditated = True

    for msg in raw.get("messages", []):
        if msg.get("sender") != "user":
            continue
        day = bucket(msg.get("timestamp") or msg.get("created_at"))
        pts = SENTIMENT_POINTS.get(str(msg.get("sentiment") or "").upper())
        if day and pts is not None:
            day.chat.append(pts)

    for t in raw.get("tasks", []):
        if not t.get("completed"):
            continue
        day = bucket(t.get("updated_at") or t.get("created_at"))
        if day:
            day.tasks_done += 1

    return [days[k] for k in sorted(days)]


# ------------------------------------------------------------------- score
def _weighted_recent(values: list[float | None], weights=(3, 2, 1)) -> float | None:
    """values[-1] is the most recent. Weighted mean over the last len(weights)."""
    pairs = [(v, w) for v, w in zip(reversed(values), weights) if v is not None]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def score_components(days: list[Day], end: int, tracks: dict[str, bool]) -> dict[str, float | None]:
    """Component scores (0–100) for the window ending at days[end]."""
    last3 = days[max(0, end - 2): end + 1]
    last7 = days[max(0, end - 6): end + 1]

    mood = _weighted_recent([d.mood for d in last3])
    if mood is None:
        vals = [d.mood for d in last7 if d.mood is not None]
        mood = mean(vals) if vals else None
    if mood is None:
        chat = [d.chat_score for d in last7 if d.chat_score is not None]
        mood = mean(chat) if chat else None

    sleep_vals = [sleep_points(d.sleep_h, d.sleep_q) for d in last3 if d.sleep_h is not None]
    if not sleep_vals:
        sleep_vals = [sleep_points(d.sleep_h, d.sleep_q) for d in last7 if d.sleep_h is not None]
    sleep = mean(sleep_vals) if sleep_vals else None

    activity = None
    if tracks.get("activity"):
        activity = min(sum(d.active_credit for d in last7) / 150 * 100, 100.0)

    mindfulness = None
    if tracks.get("mindfulness"):
        mindfulness = min(sum(1 for d in last7 if d.mindful) / 4 * 100, 100.0)

    consistency = sum(1 for d in last7 if d.logged) / max(len(last7), 1) * 100

    return {
        "mood": None if mood is None else round(mood, 1),
        "sleep": None if sleep is None else round(sleep, 1),
        "activity": None if activity is None else round(activity, 1),
        "mindfulness": None if mindfulness is None else round(mindfulness, 1),
        "consistency": round(consistency, 1),
    }


def combine(components: dict[str, float | None]) -> int | None:
    """Weighted mean of the available components. Needs at least one real
    health signal – consistency alone is not a wellness score."""
    available = {k: v for k, v in components.items() if v is not None}
    if not any(k != "consistency" for k in available):
        return None
    total_w = sum(WEIGHTS[k] for k in available)
    return round(sum(WEIGHTS[k] * v for k, v in available.items()) / total_w)


def score_label(score: int | None) -> dict[str, str]:
    if score is None:
        return {"label": "Not enough data yet", "color": "#94a3b8"}
    if score >= 80:
        return {"label": "Thriving", "color": "#10b981"}
    if score >= 65:
        return {"label": "Doing well", "color": "#22c55e"}
    if score >= 50:
        return {"label": "Holding steady", "color": "#3385fb"}
    if score >= 35:
        return {"label": "Running low", "color": "#f59e0b"}
    return {"label": "Needs care", "color": "#f43f5e"}


def tracking(days: list[Day], has_fitness_profile: bool = False) -> dict[str, bool]:
    """Which areas the user actually uses. An area they never touch is left
    out of the score rather than counted as zero."""
    return {
        "mood": any(d.mood is not None or d.chat for d in days),
        "sleep": any(d.sleep_h is not None for d in days),
        "activity": has_fitness_profile or any(d.workouts for d in days),
        "mindfulness": any(d.mindful for d in days),
    }


def score_series(days: list[Day], tracks: dict[str, bool], last_n: int = 30) -> list[dict]:
    out = []
    for i in range(max(0, len(days) - last_n), len(days)):
        comps = score_components(days, i, tracks)
        out.append({"date": days[i].date.isoformat(), "score": combine(comps)})
    return out


# ---------------------------------------------------------------- insights
@dataclass
class Rule:
    id: str
    category: str
    flag: Callable[[Day], bool | None]
    outcome: Callable[[Day], float | None]
    lag: int
    unit: str
    helps: str        # statement when effect > 0, {x} = magnitude
    hurts: str        # statement when effect < 0
    module: str


def _mood(d: Day) -> float | None:
    return d.mood


def _sleep_minutes(d: Day) -> float | None:
    return None if d.sleep_h is None else d.sleep_h * 60


RULES: list[Rule] = [
    Rule("workout_mood", "activity", lambda d: d.workouts > 0, _mood, 0, "points",
         "Your mood is {x} points higher on days you work out",
         "Your mood tends to be {x} points lower on workout days – check you're not overdoing it",
         "fitness"),
    Rule("workout_next_mood", "activity", lambda d: d.workouts > 0, _mood, 1, "points",
         "The day after a workout, your mood is {x} points higher",
         "The day after a workout, your mood dips by {x} points – recovery may need attention",
         "fitness"),
    Rule("sleep_mood", "sleep", lambda d: None if d.sleep_h is None else d.sleep_h >= 7, _mood, 0, "points",
         "After 7+ hours of sleep, your mood is {x} points higher",
         "Oddly, your mood is {x} points lower after 7+ hours of sleep",
         "sleep"),
    Rule("sleep_energy", "sleep", lambda d: None if d.sleep_h is None else d.sleep_h >= 7,
         lambda d: d.energy_avg, 0, "energy",
         "Your energy is {x} points higher (out of 10) after 7+ hours of sleep",
         "Your energy is {x} points lower after longer sleep",
         "sleep"),
    Rule("workout_sleep", "activity", lambda d: d.workouts > 0, _sleep_minutes, 1, "minutes",
         "You sleep {x} minutes longer on nights after a workout",
         "You sleep {x} minutes less after workouts – try training earlier in the day",
         "fitness"),
    Rule("meditation_mood", "mindfulness", lambda d: d.meditated, _mood, 0, "points",
         "Your mood is {x} points higher on days you meditate",
         "Your mood is {x} points lower on meditation days – you may be reaching for it on hard days, which is a good instinct",
         "meditation"),
    Rule("journal_next_mood", "mindfulness", lambda d: d.journaled, _mood, 1, "points",
         "The day after journaling, your mood is {x} points higher",
         "The day after journaling, your mood is {x} points lower",
         "journaling"),
    Rule("short_sleep_mood", "sleep", lambda d: None if d.sleep_h is None else d.sleep_h < 6, _mood, 0, "points",
         "Surprisingly, short nights haven't hurt your mood (+{x} points)",
         "After less than 6 hours of sleep, your mood drops by {x} points",
         "sleep"),
]


FAMILIES = {
    "workout_next_mood": "workout_mood",
    "short_sleep_mood": "sleep_mood",
}


def _effect(days: list[Day], rule: Rule, min_n: int = 3) -> dict | None:
    yes, no = [], []
    for i, day in enumerate(days):
        j = i + rule.lag
        if j >= len(days):
            break
        flag = rule.flag(day)
        if flag is None:
            continue
        value = rule.outcome(days[j])
        if value is None:
            continue
        (yes if flag else no).append(value)
    if len(yes) < min_n or len(no) < min_n:
        return None
    diff = mean(yes) - mean(no)
    pooled = math.sqrt((pstdev(yes) ** 2 + pstdev(no) ** 2) / 2) or 1e-9
    d = diff / pooled
    return {"diff": diff, "d": d, "n_yes": len(yes), "n_no": len(no)}


def _confidence(d: float, n_min: int) -> str | None:
    ad = abs(d)
    if n_min >= 7 and ad >= 0.5:
        return "strong"
    if n_min >= 4 and ad >= 0.35:
        return "moderate"
    if ad >= 0.25:
        return "emerging"
    return None


def insights(days: list[Day], limit: int = 5) -> list[dict]:
    found = []
    for rule in RULES:
        eff = _effect(days, rule)
        if not eff:
            continue
        conf = _confidence(eff["d"], min(eff["n_yes"], eff["n_no"]))
        if not conf:
            continue
        magnitude = abs(eff["diff"])
        if rule.unit == "energy":
            shown = f"{magnitude:.1f}"
        else:
            shown = str(round(magnitude))
        if rule.unit != "energy" and round(magnitude) == 0:
            continue
        positive = eff["diff"] > 0
        # "Short sleep" is phrased the other way round: a negative diff
        # means short sleep hurts, which is the expected (harmful) finding.
        effect_kind = "helps" if positive else "hurts"
        if rule.id == "short_sleep_mood":
            effect_kind = "hurts" if not positive else "neutral"
        found.append(
            {
                "id": rule.id,
                "category": rule.category,
                "statement": (rule.helps if positive else rule.hurts).format(x=shown),
                "effect": round(eff["diff"], 1),
                "unit": rule.unit,
                "direction": effect_kind,
                "confidence": conf,
                "effect_size": round(eff["d"], 2),
                "n_with": eff["n_yes"],
                "n_without": eff["n_no"],
                "module": rule.module,
            }
        )
    rank = {"strong": 3, "moderate": 2, "emerging": 1}
    found.sort(key=lambda f: (rank[f["confidence"]], abs(f["effect_size"])), reverse=True)

    # One insight per family: same-day and next-day workout→mood, or "7+ h
    # helps" and "under 6 h hurts", are two views of the same pattern.
    # The primary (same-day) view wins when it exists: a lagged effect on
    # alternating-day routines is mostly the same-day effect seen from the
    # other side.
    present = {f["id"] for f in found}
    out = []
    for f in found:
        primary = FAMILIES.get(f["id"])
        if primary and primary in present:
            continue
        out.append(f)
    return out[:limit]


def insight_progress(days: list[Day]) -> dict:
    """How close the user is to unlocking insights."""
    mood_days = sum(1 for d in days if d.mood is not None)
    return {
        "mood_days": mood_days,
        "needed": 10,
        "unlocked": mood_days >= 6,
    }


# ------------------------------------------------------------ early warning
def _avg(vals: Iterable[float | None]) -> float | None:
    v = [x for x in vals if x is not None]
    return mean(v) if v else None


def early_warning(days: list[Day], tracks: dict[str, bool]) -> dict:
    """Compare the last 5 days with the user's own baseline (the 21 days
    before). Several small slides together matter more than one bad day."""
    recent = days[-5:]
    base = days[-26:-5]
    signals: list[dict] = []

    rm, bm = _avg(d.mood for d in recent), _avg(d.mood for d in base)
    if (
        rm is not None and bm is not None
        and sum(d.mood is not None for d in recent) >= 2
        and sum(d.mood is not None for d in base) >= 4
        and bm - rm >= 12
    ):
        signals.append({"area": "mood", "text": f"Mood is {round(bm - rm)} points below your usual"})

    rs, bs = _avg(d.sleep_h for d in recent), _avg(d.sleep_h for d in base)
    if rs is not None and sum(d.sleep_h is not None for d in recent) >= 2:
        if bs is not None and sum(d.sleep_h is not None for d in base) >= 4 and bs - rs >= 0.75:
            signals.append({"area": "sleep", "text": f"Sleeping {round((bs - rs) * 60)} min less than usual"})
        elif rs < 6:
            signals.append({"area": "sleep", "text": f"Averaging only {rs:.1f} h of sleep"})

    if tracks.get("activity"):
        base_per5 = sum(d.active_credit for d in base) / max(len(base), 1) * 5
        recent_act = sum(d.active_credit for d in recent)
        if base_per5 >= 30 and recent_act < base_per5 * 0.4:
            signals.append({"area": "activity", "text": "Activity has dropped well below your normal"})

    if tracks.get("mindfulness"):
        if sum(d.mindful for d in base) >= 4 and not any(d.mindful for d in recent):
            signals.append({"area": "mindfulness", "text": "No meditation or journaling for 5 days"})

    rc, bc = _avg(d.chat_score for d in recent), _avg(d.chat_score for d in base)
    if rc is not None and bc is not None and bc - rc >= 20 and sum(d.chat_score is not None for d in recent) >= 2:
        signals.append({"area": "chat", "text": "Your recent conversations have felt heavier"})

    re_, be = _avg(d.energy_avg for d in recent), _avg(d.energy_avg for d in base)
    if re_ is not None and be is not None and be - re_ >= 2:
        signals.append({"area": "energy", "text": f"Energy is {be - re_:.1f}/10 below your usual"})

    areas = {s["area"] for s in signals}
    if len(signals) >= 3 or {"mood", "sleep"} <= areas:
        level = "alert"
    elif len(signals) == 2 or areas & {"mood", "sleep"}:
        level = "watch"
    elif signals:
        level = "watch"
    else:
        level = "clear"

    messages = {
        "clear": "No warning signs – your recent days look in line with your usual.",
        "watch": "A few of your signals are slipping. Nothing alarming – a good moment to be a bit kinder to yourself.",
        "alert": "Several of your patterns are sliding together, similar to how rough weeks tend to start. Let's get ahead of it.",
    }
    return {"level": level, "signals": signals, "message": messages[level]}


# -------------------------------------------------------------- today's plan
def _days_since(days: list[Day], pred: Callable[[Day], bool]) -> int | None:
    for i, d in enumerate(reversed(days)):
        if pred(d):
            return i
    return None


def daily_plan(
    days: list[Day],
    tracks: dict[str, bool],
    warning: dict,
    found_insights: list[dict],
    plan_today: dict | None = None,
) -> list[dict]:
    """Pick three actions for today from the user's current state.

    `plan_today` is today's entry from the fitness plan, if one exists.
    """
    today = days[-1]
    last_sleep = next((d.sleep_h for d in reversed(days[-2:]) if d.sleep_h is not None), None)
    recent_mood = _avg(d.mood for d in days[-3:])
    week_active = sum(d.active_credit for d in days[-7:])
    no_med = _days_since(days, lambda d: d.meditated)
    no_journal = _days_since(days, lambda d: d.journaled)
    helps = {i["id"]: i for i in found_insights if i["direction"] == "helps"}
    low = (recent_mood is not None and recent_mood < 45) or warning["level"] == "alert"
    tired = last_sleep is not None and last_sleep < 6.5

    candidates: list[tuple[int, dict]] = []

    def add(priority: int, **action):
        candidates.append((priority, action))

    # --- movement
    if plan_today and plan_today.get("type") != "rest" and not tired and not low:
        why = "It's a training day in your fitness plan."
        if "workout_mood" in helps:
            why += f" {helps['workout_mood']['statement']}."
        add(80, id="plan_workout", title=f"Today's workout: {plan_today.get('focus', 'training')}",
            detail=f"About {plan_today.get('duration_min', 30)} minutes. {why}",
            module="fitness", minutes=int(plan_today.get("duration_min") or 30), kind="move")
    elif tired or low:
        add(70, id="easy_walk", title="15-minute easy walk outside",
            detail=("You slept only %.1f h, so keep it light today." % last_sleep) if tired
            else "Gentle movement is one of the fastest mood lifts there is.",
            module="fitness", minutes=15, kind="move")
    elif tracks.get("activity") and week_active < 150:
        left = 150 - week_active
        add(65, id="move_30", title="30 minutes of movement",
            detail=f"You're {left} active minutes short of this week's 150-minute target."
            + (f" {helps['workout_mood']['statement']}." if "workout_mood" in helps else ""),
            module="fitness", minutes=30, kind="move")

    # --- mind
    if low:
        add(90, id="breathing", title="5 minutes of slow breathing",
            detail="Your mood has been lower the last few days. Slow breathing calms the nervous system within minutes.",
            module="meditation", minutes=5, kind="mind")
        if warning["level"] == "alert":
            add(72, id="talk", title="Talk it through with MindWell",
                detail="Putting things into words helps. The companion is there any time.",
                module="chat", minutes=10, kind="mind")
    if no_med is None or no_med >= 3:
        detail = "A short session resets attention and stress."
        if "meditation_mood" in helps:
            detail = helps["meditation_mood"]["statement"] + "."
        add(55 if not low else 60, id="meditate", title="10-minute meditation",
            detail=detail, module="meditation", minutes=10, kind="mind")
    if no_journal is None or no_journal >= 3 or low:
        detail = "Three lines: what happened, how it felt, one thing that went okay."
        if "journal_next_mood" in helps:
            detail = helps["journal_next_mood"]["statement"] + ". " + detail
        add(50 if not low else 70, id="journal", title="Write three lines in your journal",
            detail=detail, module="journaling", minutes=5, kind="mind")

    # --- sleep
    if tired:
        add(68, id="wind_down", title="Wind down 30 minutes earlier tonight",
            detail="Screens off, lights low. " + (helps["sleep_mood"]["statement"] + "." if "sleep_mood" in helps
                                                  else "7+ hours is the single biggest lever for mood and energy."),
            module="sleep", minutes=30, kind="sleep")

    # --- logging (fuels the twin; at most one)
    if not today.moods:
        add(85 if not candidates else 58, id="log_mood", title="Log how you feel today",
            detail="Your twin learns from daily check-ins – it takes 10 seconds.",
            module="mood", minutes=1, kind="log")
    elif today.sleep_h is None and tracks.get("sleep"):
        add(45, id="log_sleep", title="Log last night's sleep",
            detail="Sleep is 25% of your wellness score.",
            module="sleep", minutes=1, kind="log")

    if not candidates:
        add(40, id="gratitude", title="Note one thing that went well",
            detail="You're in a good stretch – noticing it helps it last.",
            module="journaling", minutes=2, kind="mind")

    candidates.sort(key=lambda c: c[0], reverse=True)
    chosen, kinds = [], {}
    for _, action in candidates:
        k = action["kind"]
        if kinds.get(k, 0) >= (2 if k == "mind" else 1):
            continue
        kinds[k] = kinds.get(k, 0) + 1
        chosen.append(action)
        if len(chosen) == 3:
            break
    return chosen


# ---------------------------------------------------------------- summaries
def snapshot(days: list[Day]) -> dict:
    last7 = days[-7:]
    streak = 0
    for d in reversed(days):
        if d.logged:
            streak += 1
        elif d is days[-1]:
            continue  # today not logged yet doesn't break the streak
        else:
            break
    return {
        "avg_mood": None if (m := _avg(d.mood for d in last7)) is None else round(m),
        "avg_sleep_h": None if (s := _avg(d.sleep_h for d in last7)) is None else round(s, 1),
        "active_minutes": sum(d.active_min for d in last7),
        "active_credit": sum(d.active_credit for d in last7),
        "workouts": sum(d.workouts for d in last7),
        "mindful_days": sum(1 for d in last7 if d.mindful),
        "logged_days": sum(1 for d in last7 if d.logged),
        "streak": streak,
    }


def week_compare(days: list[Day]) -> list[dict]:
    """This week (last 7 days) vs the 7 before, per metric."""
    this, prev = days[-7:], days[-14:-7]

    def row(key, label, fn, unit, higher_is_better=True, digits=0):
        a, b = fn(this), fn(prev)
        change = None if a is None or b is None else round(a - b, digits if digits else None)
        trend = None
        if change is not None and change != 0:
            trend = "up" if (change > 0) == higher_is_better else "down"
        fmt = (lambda v: None if v is None else round(v, digits) if digits else round(v))
        return {"key": key, "label": label, "this_week": fmt(a), "last_week": fmt(b),
                "change": change, "unit": unit, "trend": trend}

    return [
        row("mood", "Average mood", lambda ds: _avg(d.mood for d in ds), "/100"),
        row("sleep", "Average sleep", lambda ds: _avg(d.sleep_h for d in ds), "h", digits=1),
        row("active", "Active minutes", lambda ds: sum(d.active_min for d in ds) if any(d.workouts for d in days) else None, "min"),
        row("mindful", "Mindful days", lambda ds: sum(1 for d in ds if d.mindful), "days"),
        row("energy", "Average energy", lambda ds: _avg(d.energy_avg for d in ds), "/10", digits=1),
        row("logged", "Days logged", lambda ds: sum(1 for d in ds if d.logged), "days"),
    ]


def template_summary(score: int | None, delta: int | None, components: dict, warning: dict) -> str:
    if score is None:
        return ("Your twin is still getting to know you. Log your mood and sleep for a few "
                "days and your wellness score and personal insights will appear here.")
    label = score_label(score)["label"].lower()
    parts = [f"Your wellness score is {score} – {label}"]
    if delta:
        parts[0] += f", {'up' if delta > 0 else 'down'} {abs(delta)} from last week"
    parts[0] += "."
    real = {k: v for k, v in components.items() if v is not None and k != "consistency"}
    if len(real) >= 2:
        best = max(real, key=real.get)
        worst = min(real, key=real.get)
        parts.append(f"{COMPONENT_LABELS[best]} is your strongest area; "
                     f"{COMPONENT_LABELS[worst].lower()} has the most room to grow.")
    if warning["level"] != "clear":
        parts.append("A few signals are slipping, so today's plan is a gentler one.")
    return " ".join(parts)
