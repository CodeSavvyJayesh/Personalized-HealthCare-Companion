"""Fitness module: deterministic numbers, guardrails, plan validation and
the API wired to an in-memory Mongo."""

from datetime import datetime, timedelta, timezone

import pytest

import fitness_calc as calc
import fitness_library as library

BASE = {
    "age": 24,
    "sex": "male",
    "height_cm": 175,
    "weight_kg": 72,
    "activity_level": "moderate",
    "goal": "maintain",
    "experience": "beginner",
    "equipment": "none",
    "days_per_week": 3,
    "session_minutes": 40,
    "diet_preference": "veg",
    "injuries": "",
    "bmi_standard": "asian",
}


# ------------------------------------------------------------ calculator
def test_bmi_value():
    assert calc.bmi(72, 175) == 23.5


@pytest.mark.parametrize(
    "value,standard,key",
    [
        (17.0, "who", "underweight"),
        (22.0, "who", "normal"),
        (24.0, "who", "normal"),
        (24.0, "asian", "overweight"),
        (26.0, "asian", "obese"),
        (27.0, "who", "overweight"),
        (41.0, "who", "obese"),
    ],
)
def test_bmi_categories(value, standard, key):
    assert calc.bmi_category(value, standard)["key"] == key


def test_mifflin_st_jeor():
    assert calc.bmr(72, 175, 24, "male") == 1699
    assert calc.bmr(60, 162, 30, "female") == 1302  # 1301.5


def test_lose_goal_has_safe_deficit_and_floor():
    m = calc.compute_metrics({**BASE, "goal": "lose"})
    assert m["calorie_adjustment"] < 0
    assert abs(m["calorie_adjustment"]) <= 500
    assert m["target_calories"] >= max(calc.CALORIE_FLOOR["male"], m["bmr"])


def test_small_female_never_below_floor():
    m = calc.compute_metrics(
        {**BASE, "sex": "female", "height_cm": 150, "weight_kg": 50,
         "age": 45, "activity_level": "sedentary", "goal": "lose"}
    )
    assert m["target_calories"] >= 1200
    assert m["target_calories"] >= m["bmr"]


def test_underweight_cannot_get_fat_loss_plan():
    m = calc.compute_metrics({**BASE, "weight_kg": 50, "goal": "lose"})
    assert m["bmi"] < 18.5
    assert m["effective_goal"] == "gain"
    assert m["calorie_adjustment"] > 0
    assert m["guardrails"]


def test_minor_is_kept_at_maintenance():
    m = calc.compute_metrics({**BASE, "age": 16, "weight_kg": 85, "goal": "lose"})
    assert m["effective_goal"] == "maintain"
    assert m["calorie_adjustment"] == 0
    assert m["body_fat_pct"] is None


def test_macros_add_up_roughly_to_target():
    m = calc.compute_metrics({**BASE, "goal": "gain"})
    mac = m["macros"]
    kcal = mac["protein_g"] * 4 + mac["carbs_g"] * 4 + mac["fat_g"] * 9
    assert abs(kcal - m["target_calories"]) < 20


def test_protein_uses_reference_weight_when_obese():
    m = calc.compute_metrics({**BASE, "weight_kg": 130, "goal": "lose"})
    assert m["macros"]["protein_g"] < 130 * 1.8


def test_healthy_range_and_distance():
    m = calc.compute_metrics({**BASE, "weight_kg": 80})
    assert m["healthy_weight_min"] < m["healthy_weight_max"]
    assert m["kg_to_healthy_range"] < 0


def test_calories_burned_and_who_credit():
    assert calc.calories_burned("cardio", "moderate", 60, 70) == 490
    assert calc.activity_minutes_credit("high", 30) == 60
    assert calc.activity_minutes_credit("moderate", 30) == 30


# -------------------------------------------------------------- library
@pytest.mark.parametrize("days", [2, 3, 4, 5, 6])
@pytest.mark.parametrize("equipment", ["none", "home", "gym"])
def test_rule_based_schedule_shape(days, equipment):
    profile = {**BASE, "days_per_week": days, "equipment": equipment}
    plan = library.rule_based_plan(profile, calc.compute_metrics(profile), {})
    schedule = plan["workout"]["schedule"]
    assert [d["day"] for d in schedule] == library.WEEKDAYS
    assert sum(d["type"] != "rest" for d in schedule) == days
    assert all(d["exercises"] for d in schedule)


@pytest.mark.parametrize("pref", ["veg", "eggetarian", "non_veg", "vegan", "jain"])
def test_built_in_meals_respect_preference(pref):
    profile = {**BASE, "diet_preference": pref}
    diet = library.build_diet(profile, calc.compute_metrics(profile))
    for meal in diet["meals"]:
        assert meal["options"]
        for option in meal["options"]:
            assert not library.violates_preference(option, pref), (pref, option)


def test_meal_calories_sum_to_target():
    m = calc.compute_metrics(BASE)
    diet = library.build_diet(BASE, m)
    assert abs(sum(x["calories"] for x in diet["meals"]) - m["target_calories"]) <= 30


def test_injury_filter_removes_knee_loading_moves():
    profile = {**BASE, "injuries": "left knee pain", "days_per_week": 4}
    workout = library.build_workout(profile, "maintain")
    names = [e["name"].lower() for d in workout["schedule"] for e in d["exercises"]]
    assert not any("lunge" in n or "jump" in n for n in names)
    assert workout["avoided_for_injury"]


def test_preference_check_handles_negation_and_plant_milks():
    assert not library.violates_preference("Chilla (no onion/garlic) + curd", "jain")
    assert library.violates_preference("Aloo paratha", "jain")
    assert not library.violates_preference("Oats in soy milk with peanut butter", "vegan")
    assert library.violates_preference("Paneer tikka", "vegan")
    assert not library.violates_preference("Baingan (eggplant) bharta", "veg")


def test_extract_json_from_fenced_and_trailing_comma():
    text = 'Sure!\n```json\n{"summary": "hi", "tips": ["a",],}\n```'
    assert library.extract_json(text) == {"summary": "hi", "tips": ["a"]}
    assert library.extract_json("no json here") is None


def _ai_plan(meal_option="Paneer bhurji + 2 rotis"):
    schedule = []
    for i, day in enumerate(library.WEEKDAYS):
        train = i in (0, 2, 4)
        schedule.append({
            "day": day,
            "focus": "Full body" if train else "Rest",
            "type": "strength" if train else "rest",
            "duration_min": 40,
            "exercises": [{"name": "Squats", "sets": "3", "reps": "10", "rest_sec": "60"}] if train else [],
        })
    return {
        "summary": "Your plan",
        "workout": {"schedule": schedule, "warmup": ["walk"], "cooldown": ["stretch"], "progression": "add reps"},
        "diet": {"meals": [
            {"name": "Breakfast", "calories": 900, "options": [meal_option, "Chicken sandwich"]},
            {"name": "Lunch", "calories": 900, "options": ["Dal rice"]},
            {"name": "Dinner", "calories": 900, "options": ["Khichdi"]},
        ]},
        "tips": ["drink water"],
        "mind_body": ["walk when stressed"],
    }


def test_normalise_forces_numbers_and_strips_forbidden_food():
    m = calc.compute_metrics(BASE)
    fallback = library.rule_based_plan(BASE, m, {})
    plan, patched = library.normalise_plan(_ai_plan(), fallback, BASE, m)
    assert plan["diet"]["daily_calories"] == m["target_calories"]
    assert plan["diet"]["macros"] == m["macros"]
    options = [o for meal in plan["diet"]["meals"] for o in meal["options"]]
    assert "Chicken sandwich" not in options
    assert any("removed" in p for p in patched)
    total = sum(meal["calories"] for meal in plan["diet"]["meals"])
    assert abs(total - m["target_calories"]) <= 30
    assert plan["workout"]["schedule"][0]["exercises"][0]["sets"] == 3


def test_normalise_falls_back_on_garbage():
    m = calc.compute_metrics(BASE)
    fallback = library.rule_based_plan(BASE, m, {})
    plan, patched = library.normalise_plan(None, fallback, BASE, m)
    assert plan is fallback and patched == ["all"]
    plan, patched = library.normalise_plan({"summary": "x"}, fallback, BASE, m)
    assert "workout" in patched and "diet" in patched


# ------------------------------------------------------------------- API
mongomock = pytest.importorskip("mongomock")


@pytest.fixture()
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import fitness
    import llm
    from auth import get_current_user

    db = mongomock.MongoClient().db
    for name in (
        "fitness_profiles_collection",
        "fitness_metrics_collection",
        "fitness_plans_collection",
        "fitness_workouts_collection",
        "moods_collection",
        "sleep_collection",
        "safety_events_collection",
    ):
        monkeypatch.setattr(fitness, name, db[name])

    def offline(*args, **kwargs):
        raise llm.LLMUnavailable("offline in tests")

    monkeypatch.setattr(fitness.llm, "chat", offline)

    app = FastAPI()
    app.include_router(fitness.router)
    app.dependency_overrides[get_current_user] = lambda: "asha@example.com"
    return TestClient(app)


def test_profile_plan_and_workout_flow(client):
    r = client.get("/fitness/profile/asha@example.com")
    assert r.status_code == 200 and r.json()["profile"] is None

    r = client.put("/fitness/profile", json={**BASE, "goal": "lose"})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["bmi"] == 23.5
    assert len(body["history"]) == 1

    r = client.post("/fitness/weight", json={"weight_kg": 71})
    assert r.json()["metrics"]["bmi"] == 23.2
    assert len(r.json()["history"]) == 2

    r = client.post("/fitness/plan", json={})
    assert r.status_code == 200
    assert r.json()["source"] == "rule_based"
    assert len(r.json()["plan"]["workout"]["schedule"]) == 7

    r = client.get("/fitness/plan/asha@example.com")
    assert r.json()["plan"] is not None

    r = client.post("/fitness/workouts", json={
        "activity": "Full body A", "category": "strength",
        "duration_min": 40, "intensity": "high",
    })
    assert r.status_code == 200 and r.json()["calories"] > 0
    workout_id = r.json()["workout_id"]

    stats = client.get("/fitness/workouts/asha@example.com").json()["stats"]
    assert stats["week_sessions"] == 1
    assert stats["week_active_minutes"] == 80
    assert stats["streak_days"] == 1
    assert len(stats["weekly"]) == 8

    assert client.delete(f"/fitness/workouts/{workout_id}").status_code == 200
    assert client.delete(f"/fitness/workouts/{workout_id}").status_code == 404


def test_cannot_read_someone_elses_fitness_data(client):
    assert client.get("/fitness/profile/someone@else.com").status_code == 403


def test_plan_requires_profile(client):
    assert client.post("/fitness/plan", json={}).status_code == 404


def test_coach_refuses_severe_restriction_without_llm(client):
    r = client.post("/fitness/coach", json={"question": "how do I eat 500 calories a day to lose weight fast"})
    body = r.json()
    assert body["source"] == "safety"
    assert "can't help" in body["answer"]


def test_coach_offline_fallback(client):
    r = client.post("/fitness/coach", json={"question": "how much protein do I need?"})
    assert r.json()["source"] == "fallback"


def test_streak_counts_consecutive_days():
    import fitness

    now = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
    docs = [
        {"created_at": now - timedelta(days=d), "duration_min": 30, "intensity": "moderate", "calories": 100}
        for d in (0, 1, 2, 4)
    ]
    stats = fitness.workout_stats(docs, now)
    assert stats["streak_days"] == 3


def test_no_duplicate_exercises_in_a_day():
    for injuries in ("", "lower back", "knee and shoulder"):
        for equipment in ("none", "home", "gym"):
            profile = {**BASE, "injuries": injuries, "equipment": equipment, "days_per_week": 4, "session_minutes": 60}
            for day in library.build_workout(profile, "maintain")["schedule"]:
                names = [e["name"] for e in day["exercises"]]
                assert len(names) == len(set(names)), (injuries, equipment, names)
