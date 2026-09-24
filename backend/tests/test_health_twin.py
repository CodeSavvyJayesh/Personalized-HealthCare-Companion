"""Personal Health Twin: engine maths, insights, early warning, daily plan,
API flow on an in-memory Mongo, and the privacy guarantee that journal and
chat text are never loaded."""

import random
from datetime import date, datetime, timedelta, timezone

import pytest

import twin_engine as engine

TODAY = date(2026, 9, 24)
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _ts(days_ago: int, hour: int = 6) -> datetime:
    # 06:00 UTC = 11:30 IST, safely inside the same local day
    return NOW.replace(hour=hour) - timedelta(days=days_ago)


def synthetic(n=40, seed=7, slide=False):
    """Workout days → better mood; short sleep → worse mood."""
    rnd = random.Random(seed)
    raw = {k: [] for k in ("moods", "journals", "sleep", "workouts", "meditation", "messages", "tasks")}
    for ago in range(n - 1, -1, -1):
        worked = ago % 2 == 0
        short = ago % 5 == 0
        if slide and ago < 5:
            worked, short = False, True
        mood = "happy" if worked and not short else ("sad" if short else rnd.choice(["neutral", "calm"]))
        raw["moods"].append({"mood": mood, "energy": 3 if short else 7, "created_at": _ts(ago)})
        raw["sleep"].append({"bed_time": "01:30" if short else "23:00", "wake_time": "06:30",
                             "quality": "Poor" if short else "Good", "created_at": _ts(ago)})
        if worked:
            raw["workouts"].append({"duration_min": 40, "intensity": "moderate", "created_at": _ts(ago)})
        if ago % 3 == 0 and not (slide and ago < 5):
            raw["meditation"].append({"date": (TODAY - timedelta(days=ago)).isoformat(), "created_at": _ts(ago)})
    return raw


# ---------------------------------------------------------------- basics
def test_mood_and_sleep_mapping():
    assert engine.mood_points("happy") == 100
    assert engine.mood_points("anxious") == 0
    assert engine.mood_points("unknown") is None
    assert engine.sleep_hours("23:00", "07:00") == 8
    assert engine.sleep_hours("bad", "07:00") is None
    assert engine.sleep_quality_value("Good") == 4
    assert engine.sleep_quality_value(3) == 3
    assert engine.sleep_points(8) == 100
    assert engine.sleep_points(4) < engine.sleep_points(6) < engine.sleep_points(7)


def test_local_date_uses_offset():
    late = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)  # 01:30 IST next day
    assert engine.local_date(late, 330) == date(2026, 9, 24)
    assert engine.local_date(late, 0) == date(2026, 9, 23)


def test_build_days_buckets_everything():
    days = engine.build_days(synthetic(10), TODAY, 10)
    assert len(days) == 10 and days[-1].date == TODAY
    assert all(d.mood is not None for d in days)
    assert all(d.sleep_h is not None for d in days)
    assert sum(d.workouts for d in days) == 5


# ----------------------------------------------------------------- score
def test_score_in_range_and_labelled():
    days = engine.build_days(synthetic(), TODAY, 40)
    tracks = engine.tracking(days)
    comps = engine.score_components(days, len(days) - 1, tracks)
    score = engine.combine(comps)
    assert 0 <= score <= 100
    assert engine.score_label(score)["label"]
    assert set(comps) == set(engine.WEIGHTS)


def test_untracked_areas_are_excluded_not_zeroed():
    raw = {"moods": [{"mood": "happy", "created_at": _ts(0)}]}
    days = engine.build_days(raw, TODAY, 14)
    tracks = engine.tracking(days)
    comps = engine.score_components(days, len(days) - 1, tracks)
    assert comps["activity"] is None and comps["sleep"] is None
    # mood 100 and consistency 1/7 → still a high-ish score, not dragged to 0
    assert engine.combine(comps) > 70


def test_no_health_signal_means_no_score():
    days = engine.build_days({"tasks": [{"completed": True, "updated_at": _ts(0)}]}, TODAY, 14)
    comps = engine.score_components(days, len(days) - 1, engine.tracking(days))
    assert engine.combine(comps) is None


def test_trend_series_length():
    days = engine.build_days(synthetic(), TODAY, 40)
    series = engine.score_series(days, engine.tracking(days), 30)
    assert len(series) == 30 and series[-1]["date"] == TODAY.isoformat()


# -------------------------------------------------------------- insights
def test_insights_find_the_planted_patterns():
    days = engine.build_days(synthetic(), TODAY, 40)
    found = {i["id"]: i for i in engine.insights(days, limit=10)}
    assert "workout_mood" in found
    assert found["workout_mood"]["direction"] == "helps"
    assert found["workout_mood"]["effect"] > 0
    assert any(i in found for i in ("sleep_mood", "short_sleep_mood"))
    for i in found.values():
        assert i["confidence"] in {"strong", "moderate", "emerging"}
        assert i["n_with"] >= 3 and i["n_without"] >= 3


def test_no_insights_from_noise_or_tiny_data():
    raw = {"moods": [{"mood": "neutral", "created_at": _ts(a)} for a in range(4)]}
    days = engine.build_days(raw, TODAY, 20)
    assert engine.insights(days) == []
    assert engine.insight_progress(days)["unlocked"] is False


# ---------------------------------------------------------- early warning
def test_warning_clear_on_stable_data():
    days = engine.build_days(synthetic(), TODAY, 40)
    assert engine.early_warning(days, engine.tracking(days))["level"] in {"clear", "watch"}


def test_warning_alert_on_multi_signal_slide():
    days = engine.build_days(synthetic(slide=True), TODAY, 40)
    w = engine.early_warning(days, engine.tracking(days))
    assert w["level"] == "alert"
    areas = {s["area"] for s in w["signals"]}
    assert {"mood", "sleep"} <= areas


# ------------------------------------------------------------------ plan
def test_plan_is_three_distinct_actions():
    days = engine.build_days(synthetic(), TODAY, 40)
    tracks = engine.tracking(days)
    plan = engine.daily_plan(days, tracks, engine.early_warning(days, tracks), engine.insights(days))
    assert 1 <= len(plan) <= 3
    assert len({a["id"] for a in plan}) == len(plan)
    assert all(a["module"] for a in plan)


def test_plan_is_gentle_when_sliding():
    days = engine.build_days(synthetic(slide=True), TODAY, 40)
    tracks = engine.tracking(days)
    warning = engine.early_warning(days, tracks)
    plan = engine.daily_plan(days, tracks, warning, [], {"type": "strength", "focus": "Legs", "duration_min": 45})
    ids = {a["id"] for a in plan}
    assert "plan_workout" not in ids          # no heavy session on a bad stretch
    assert "breathing" in ids


def test_plan_uses_fitness_plan_on_good_days():
    raw = synthetic()
    days = engine.build_days(raw, TODAY, 40)
    days[-1].sleep_h = 8
    tracks = engine.tracking(days)
    plan = engine.daily_plan(days, tracks, {"level": "clear", "signals": []}, [],
                             {"type": "strength", "focus": "Upper body", "duration_min": 40})
    assert plan[0]["id"] in {"plan_workout", "log_mood"} or any(a["id"] == "plan_workout" for a in plan)


def test_week_compare_rows():
    days = engine.build_days(synthetic(), TODAY, 40)
    rows = engine.week_compare(days)
    assert {r["key"] for r in rows} >= {"mood", "sleep", "active", "mindful"}
    for r in rows:
        assert r["trend"] in {None, "up", "down"}


# ------------------------------------------------------------------- API
mongomock = pytest.importorskip("mongomock")

USER = "twin@example.com"


@pytest.fixture()
def api(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import llm
    import twin
    from auth import get_current_user

    db = mongomock.MongoClient().db
    for name in (
        "fitness_plans_collection", "fitness_profiles_collection", "fitness_workouts_collection",
        "journals_collection", "meditation_collection", "messages_collection", "moods_collection",
        "safety_events_collection", "sleep_collection", "tasks_collection",
        "twin_actions_collection", "twin_reports_collection",
    ):
        monkeypatch.setattr(twin, name, db[name])

    def offline(*a, **k):
        raise llm.LLMUnavailable("offline")

    monkeypatch.setattr(twin.llm, "chat", offline)
    monkeypatch.setattr(twin, "utcnow", lambda: NOW)

    raw = synthetic()
    for key, coll in (("moods", "moods_collection"), ("sleep", "sleep_collection"),
                      ("workouts", "fitness_workouts_collection"), ("meditation", "meditation_collection")):
        for doc in raw[key]:
            db[coll].insert_one({"user_id": USER, **doc})
    db["journals_collection"].insert_one(
        {"user_id": USER, "mood": "happy", "content": "PRIVATE JOURNAL TEXT", "created_at": _ts(1)})
    db["messages_collection"].insert_one(
        {"user_id": USER, "sender": "user", "text": "PRIVATE CHAT TEXT", "sentiment": "POSITIVE", "timestamp": _ts(1)})

    app = FastAPI()
    app.include_router(twin.router)
    app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app), twin, db


def test_overview_shape(api):
    client, _, _ = api
    body = client.get(f"/twin/overview/{USER}").json()
    assert body["success"] and 0 <= body["score"] <= 100
    assert len(body["components"]) == 5
    assert len(body["trend"]) == 30
    assert body["insights"]
    assert 1 <= len(body["plan"]) <= 3
    assert body["warning"]["level"] in {"clear", "watch", "alert"}
    assert "_days" not in body
    assert body["support"] is None


def test_overview_is_owner_only(api):
    client, _, _ = api
    assert client.get("/twin/overview/someone@else.com").status_code == 403


def test_private_text_is_never_loaded(api):
    _, twin, _ = api
    raw = twin._load_raw(USER, NOW)
    blob = str(raw)
    assert "PRIVATE JOURNAL TEXT" not in blob
    assert "PRIVATE CHAT TEXT" not in blob
    assert raw["journals"] and raw["messages"]


def test_toggle_action(api):
    client, _, _ = api
    assert client.post("/twin/actions/breathing/toggle").json()["done"] is True
    plan_ids = [a["id"] for a in client.get(f"/twin/overview/{USER}").json()["plan"]]
    assert client.post("/twin/actions/breathing/toggle").json()["done"] is False
    assert client.post("/twin/actions/" + "x" * 50 + "/toggle").status_code == 400
    assert plan_ids


def test_weekly_report_fallback_and_cache(api):
    client, _, db = api
    first = client.post("/twin/report", json={}).json()
    assert first["source"] == "template"
    assert first["narrative"] and first["focus"]
    assert len(first["compare"]) == 6
    again = client.post("/twin/report", json={}).json()
    assert again["created_at"] == first["created_at"]           # served from cache
    latest = client.get(f"/twin/report/{USER}").json()["report"]
    assert latest["week_start"] == first["week_start"]


def test_support_card_after_escalation(api):
    client, _, db = api
    db["safety_events_collection"].insert_one({"user_id": USER, "tier": 2, "created_at": NOW - timedelta(days=2)})
    body = client.get(f"/twin/overview/{USER}").json()
    assert body["support"] and "resources" in body["support"]


def test_sleep_schema_accepts_labels_and_numbers():
    from pydantic import ValidationError

    from schemas import SleepIn

    assert SleepIn(bed_time="23:00", wake_time="07:00", quality="Good").quality == "Good"
    assert SleepIn(bed_time="23:00", wake_time="07:00", quality=4).quality == 4
    with pytest.raises(ValidationError):
        SleepIn(bed_time="23:00", wake_time="07:00", quality=9)
    with pytest.raises(ValidationError):
        SleepIn(bed_time="23:00", wake_time="07:00", quality="Great")
