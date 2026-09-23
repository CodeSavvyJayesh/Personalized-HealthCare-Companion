"""Plan building for the fitness module.

Three jobs:

1. `rule_based_plan`  – a complete, sensible plan with no model at all. It
   is the fallback when the LLM is down, and the skeleton the AI plan is
   checked against.
2. `ai_messages`      – the prompt that asks the LLM for a personalised plan
   as strict JSON, with the calorie and macro numbers handed to it.
3. `normalise_plan`   – takes whatever the model returned and forces it into
   the exact shape the frontend renders. Numbers are overwritten with the
   deterministic ones, meal options that break the user's diet preference
   are dropped, and any section the model got wrong is filled from the
   rule-based plan. The UI never has to guess what it received.
"""

from __future__ import annotations

import json
import re
from typing import Any

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ------------------------------------------------------------------ exercises
# (name, coaching cue). Grouped by equipment and movement pattern.
EXERCISES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "none": {
        "legs": [
            ("Bodyweight squats", "Sit back, chest up, knees track over toes"),
            ("Reverse lunges", "Step back softly, front knee over mid-foot"),
            ("Wall sit", "Thighs parallel to the floor, back flat on the wall"),
            ("Step-ups on a sturdy stair", "Drive through the heel of the top foot"),
        ],
        "hinge": [
            ("Glute bridges", "Squeeze glutes at the top, ribs down"),
            ("Single-leg glute bridge", "Keep hips level"),
            ("Bodyweight good mornings", "Soft knees, hinge from the hips"),
        ],
        "push": [
            ("Push-ups", "Body in one straight line; drop to knees if needed"),
            ("Incline push-ups (hands on a bed or table)", "Easier than floor push-ups"),
            ("Pike push-ups", "Hips high, lower the head between the hands"),
            ("Chair dips", "Elbows point back, shoulders away from ears"),
        ],
        "pull": [
            ("Towel rows under a sturdy table", "Pull chest to the table edge"),
            ("Superman hold", "Lift chest and legs, hold 2 seconds"),
            ("Reverse snow angels", "Face down, sweep arms slowly"),
        ],
        "core": [
            ("Plank", "Brace like you're about to be poked in the stomach"),
            ("Dead bug", "Lower back stays pressed into the floor"),
            ("Bicycle crunches", "Slow and controlled, no neck pulling"),
            ("Side plank", "Hips high, body in a straight line"),
        ],
        "cardio": [
            ("Brisk walk or easy jog", "Conversational pace"),
            ("Jumping jacks intervals", "30 s on / 30 s easy"),
            ("Mountain climbers", "Hips level, quick feet"),
            ("High knees", "Stay light on the balls of your feet"),
        ],
    },
    "home": {
        "legs": [
            ("Dumbbell goblet squats", "Hold the dumbbell at the chest, elbows down"),
            ("Dumbbell reverse lunges", "Control the step back"),
            ("Dumbbell step-ups", "Full foot on the step"),
            ("Resistance-band lateral walks", "Band above the knees, small steps"),
        ],
        "hinge": [
            ("Dumbbell Romanian deadlifts", "Weights slide down the thighs, flat back"),
            ("Dumbbell hip thrusts", "Upper back on a bench or sofa"),
            ("Band good mornings", "Hinge, don't squat"),
        ],
        "push": [
            ("Dumbbell floor press", "Elbows at 45 degrees"),
            ("Push-ups", "Add a pause at the bottom when easy"),
            ("Seated dumbbell shoulder press", "Don't arch the lower back"),
            ("Band chest press", "Band anchored behind you"),
        ],
        "pull": [
            ("One-arm dumbbell rows", "Pull the elbow toward the hip"),
            ("Resistance-band rows", "Squeeze shoulder blades together"),
            ("Band pull-aparts", "Arms straight, slow return"),
            ("Dumbbell bicep curls", "No swinging"),
        ],
        "core": [
            ("Plank", "Brace and breathe"),
            ("Dead bug", "Lower back on the floor"),
            ("Russian twists (light dumbbell)", "Rotate from the ribs"),
            ("Side plank", "Hips high"),
        ],
        "cardio": [
            ("Skipping rope intervals", "30 s on / 30 s rest"),
            ("Dumbbell thrusters", "Squat into a press, steady rhythm"),
            ("Brisk walk or easy jog", "Conversational pace"),
            ("Burpees (step-back version is fine)", "Move smoothly, not frantically"),
        ],
    },
    "gym": {
        "legs": [
            ("Barbell back squats", "Brace, sit between the hips"),
            ("Leg press", "Don't lock the knees at the top"),
            ("Walking lunges", "Tall torso"),
            ("Leg extensions", "Pause at the top"),
        ],
        "hinge": [
            ("Romanian deadlifts", "Hinge, bar close to the legs"),
            ("Hip thrusts", "Chin tucked, full lockout"),
            ("Lying leg curls", "Slow lowering"),
            ("Conventional deadlifts", "Neutral spine, push the floor away"),
        ],
        "push": [
            ("Barbell bench press", "Shoulder blades pinned back"),
            ("Incline dumbbell press", "30-degree bench"),
            ("Overhead press", "Glutes tight, press straight up"),
            ("Cable triceps pushdowns", "Elbows stay pinned"),
        ],
        "pull": [
            ("Lat pulldowns", "Pull to the upper chest"),
            ("Seated cable rows", "Chest tall, no rocking"),
            ("Pull-ups or assisted pull-ups", "Full hang to chin over bar"),
            ("Face pulls", "Pull to the forehead, elbows high"),
        ],
        "core": [
            ("Cable woodchops", "Rotate through the torso"),
            ("Hanging knee raises", "No swinging"),
            ("Plank", "Brace and breathe"),
            ("Pallof press", "Resist the rotation"),
        ],
        "cardio": [
            ("Incline treadmill walk", "Hands off the rails"),
            ("Rowing machine intervals", "Legs, then back, then arms"),
            ("Stationary bike intervals", "30 s hard / 90 s easy"),
            ("Elliptical steady state", "Conversational pace"),
        ],
    },
}

MOBILITY = [
    "Cat-cow stretch – 10 slow reps",
    "Hip flexor stretch – 30 s each side",
    "Thread-the-needle – 5 each side",
    "Child's pose with deep breathing – 60 s",
    "Hamstring stretch – 30 s each side",
]

WARMUP = [
    "3–5 min brisk walk, march or light skipping",
    "Arm circles and shoulder rolls – 10 each direction",
    "Leg swings – 10 each leg, front-to-back and side-to-side",
    "Hip circles and bodyweight squats – 10 reps",
]

COOLDOWN = [
    "2–3 min easy walk to bring the heart rate down",
    "Hamstring and quad stretch – 30 s each",
    "Chest and shoulder stretch – 30 s each",
    "Box breathing (4-4-4-4) for 1–2 minutes",
]

INJURY_AVOID = {
    "knee": ["lunge", "jump", "burpee", "high knees", "step-up", "leg extension", "wall sit"],
    "back": ["deadlift", "good morning", "superman", "back squat", "russian twist", "thruster"],
    "shoulder": ["overhead", "pike", "dip", "shoulder press", "thruster", "pull-up"],
    "wrist": ["push-up", "plank", "mountain climber", "burpee", "floor press", "dip"],
    "ankle": ["jump", "skipping", "high knees", "burpee", "lunge"],
}

# ----------------------------------------------------------------- splits
_DAY_INDEXES = {
    2: [0, 3],
    3: [0, 2, 4],
    4: [0, 1, 3, 4],
    5: [0, 1, 2, 4, 5],
    6: [0, 1, 2, 3, 4, 5],
}

_TEMPLATES = {
    "full_a": ("Full body strength A", ["legs", "push", "pull", "hinge", "core", "core"]),
    "full_b": ("Full body strength B", ["hinge", "pull", "push", "legs", "core", "cardio"]),
    "full_c": ("Full body strength C", ["legs", "pull", "push", "hinge", "core", "cardio"]),
    "upper": ("Upper body", ["push", "pull", "push", "pull", "core", "core"]),
    "lower": ("Lower body & core", ["legs", "hinge", "legs", "hinge", "core", "core"]),
    "push": ("Push – chest, shoulders, triceps", ["push", "push", "push", "push", "core", "core"]),
    "pull": ("Pull – back & biceps", ["pull", "pull", "pull", "pull", "core", "core"]),
    "legs": ("Legs & glutes", ["legs", "hinge", "legs", "hinge", "core", "core"]),
    "conditioning": ("Cardio conditioning & core", ["cardio", "cardio", "core", "cardio", "core", "core"]),
}


def _split(days: int, goal: str) -> list[str]:
    if days <= 2:
        return ["full_a", "full_b"]
    if days == 3:
        return ["full_a", "conditioning", "full_b"] if goal == "fitness" else ["full_a", "full_b", "full_c"]
    if days == 4:
        return ["upper", "lower", "upper", "lower"] if goal != "fitness" else ["full_a", "conditioning", "full_b", "conditioning"]
    if days == 5:
        return ["upper", "lower", "conditioning", "upper", "lower"]
    return ["push", "pull", "legs", "push", "pull", "legs"]


def _scheme(experience: str, goal: str, minutes: int) -> dict[str, Any]:
    if experience == "advanced":
        sets, reps, rest = 4, "6-10", 90
    elif experience == "intermediate":
        sets, reps, rest = 3, "8-12", 75
    else:
        sets, reps, rest = (3 if minutes >= 40 else 2), "10-12", 60
    if goal == "lose":
        reps, rest = "12-15", 45 if experience != "beginner" else 60
    if goal == "fitness":
        reps, rest = "10-15", 60
    return {"sets": sets, "reps": reps, "rest": rest}


def _exercise_count(minutes: int) -> int:
    if minutes <= 25:
        return 3
    if minutes <= 35:
        return 4
    if minutes <= 50:
        return 5
    return 6


def _injury_terms(injuries: str) -> list[str]:
    text = (injuries or "").lower()
    terms: list[str] = []
    for area, avoid in INJURY_AVOID.items():
        if area in text:
            terms.extend(avoid)
    return terms


def _pick(pool: list[tuple[str, str]], offset: int, avoid: list[str], used: set[str]):
    safe = [ex for ex in pool if not any(term in ex[0].lower() for term in avoid)]
    candidates = safe or pool
    for i in range(len(candidates)):
        ex = candidates[(offset + i) % len(candidates)]
        if ex[0] not in used:
            return ex
    return candidates[offset % len(candidates)]


def build_workout(profile: dict[str, Any], goal: str) -> dict[str, Any]:
    equipment = profile.get("equipment", "none")
    library = EXERCISES.get(equipment, EXERCISES["none"])
    days = int(profile.get("days_per_week", 3))
    minutes = int(profile.get("session_minutes", 40))
    experience = profile.get("experience", "beginner")
    avoid = _injury_terms(profile.get("injuries", ""))
    scheme = _scheme(experience, goal, minutes)
    count = _exercise_count(minutes)

    split = _split(days, goal)
    training_days = dict(zip(_DAY_INDEXES.get(days, _DAY_INDEXES[3]), split))

    schedule = []
    for idx, day in enumerate(WEEKDAYS):
        key = training_days.get(idx)
        if key is None:
            active = goal in {"lose", "fitness"}
            schedule.append(
                {
                    "day": day,
                    "focus": "Active recovery" if active else "Rest & mobility",
                    "type": "rest",
                    "duration_min": 30 if active else 15,
                    "exercises": [
                        {
                            "name": "Easy walk" if active else "Gentle mobility flow",
                            "sets": 1,
                            "reps": "25-35 min" if active else "10-15 min",
                            "rest_sec": 0,
                            "notes": "Aim for 7,000–8,000 steps today" if active
                            else "Recovery is when you actually get stronger",
                        }
                    ],
                }
            )
            continue

        title, patterns = _TEMPLATES[key]
        used: set[str] = set()
        exercises = []
        for slot, pattern in enumerate(patterns):
            if len(exercises) >= count:
                break
            name, cue = _pick(library[pattern], idx + slot, avoid, used)
            if name in used:
                continue  # pool exhausted (e.g. after injury filtering)
            used.add(name)
            if pattern == "cardio":
                reps, sets, rest = ("8-12 min" if key != "conditioning" else "10-15 min"), 1, 0
            elif pattern == "core" and any(w in name.lower() for w in ("plank", "hold", "wall sit")):
                reps, sets, rest = "30-45 s", scheme["sets"], 45
            else:
                reps, sets, rest = scheme["reps"], scheme["sets"], scheme["rest"]
            exercises.append(
                {"name": name, "sets": sets, "reps": reps, "rest_sec": rest, "notes": cue}
            )

        if goal == "lose" and key != "conditioning":
            exercises.append(
                {
                    "name": "Cardio finisher",
                    "sets": 1,
                    "reps": "8-10 min",
                    "rest_sec": 0,
                    "notes": "Intervals: 40 s brisk / 20 s easy",
                }
            )

        schedule.append(
            {
                "day": day,
                "focus": title,
                "type": "cardio" if key == "conditioning" else "strength",
                "duration_min": minutes,
                "exercises": exercises,
            }
        )

    progression = {
        "beginner": "Weeks 1–2: learn the movements with easy effort. Weeks 3–4: add one set "
        "or 2 reps per exercise. When the top of the rep range feels easy for all sets, "
        "move to a harder variation or heavier weight.",
        "intermediate": "Use double progression: when you hit the top of the rep range on every "
        "set, add 2.5–5% load next session. Take a lighter deload week every 5–6 weeks.",
        "advanced": "Run 4-week waves: add load each week at the same reps, then deload in week "
        "4. Track your top sets and keep 1–2 reps in reserve on most sets.",
    }[experience if experience in {"beginner", "intermediate", "advanced"} else "beginner"]

    return {
        "schedule": schedule,
        "warmup": WARMUP,
        "cooldown": COOLDOWN,
        "progression": progression,
        "avoided_for_injury": bool(avoid),
    }


# ---------------------------------------------------------------------- diet
MEAL_SPLIT = [
    ("Breakfast", "8:00 AM", 0.25),
    ("Mid-morning snack", "11:00 AM", 0.10),
    ("Lunch", "1:30 PM", 0.30),
    ("Evening snack", "5:00 PM", 0.10),
    ("Dinner", "8:00 PM", 0.25),
]

_VEG = {
    "Breakfast": [
        "Vegetable poha with peanuts + 1 glass milk",
        "Moong dal chilla (2) with mint chutney + curd",
        "Vegetable oats upma + 1 fruit",
        "Paneer bhurji with 2 multigrain rotis",
    ],
    "Mid-morning snack": [
        "1 fruit (apple/guava/orange) + 10 almonds",
        "Roasted chana (30 g) + buttermilk",
        "Greek yogurt or hung curd with berries",
    ],
    "Lunch": [
        "2 rotis + dal + seasonal sabzi + salad + curd",
        "Brown rice + rajma + cucumber raita + salad",
        "Jowar bhakri + chana masala + sabzi + salad",
    ],
    "Evening snack": [
        "Sprouts chaat with lemon",
        "Makhana roasted in 1 tsp ghee",
        "Buttermilk + a handful of peanuts",
    ],
    "Dinner": [
        "Paneer tikka + vegetable soup + 1 roti",
        "Khichdi (dal + rice + vegetables) + curd",
        "Tofu/paneer stir-fry with vegetables + 1 roti",
    ],
}

_EGG_EXTRA = {
    "Breakfast": ["2-egg vegetable omelette + 2 slices whole-wheat toast"],
    "Mid-morning snack": ["2 boiled eggs + 1 fruit"],
    "Dinner": ["Egg curry (2 eggs) + 1 roti + salad"],
}

_NONVEG_EXTRA = {
    "Lunch": ["2 rotis + chicken curry (120 g) + salad + curd", "Rice + fish curry + sabzi"],
    "Dinner": ["Grilled chicken (120 g) + sautéed vegetables + 1 roti", "Fish tikka + dal + salad"],
}

_VEGAN = {
    "Breakfast": [
        "Vegetable poha with peanuts + soy milk",
        "Moong dal chilla (2) with mint chutney",
        "Oats cooked in soy milk with banana and seeds",
        "Tofu bhurji with 2 rotis",
    ],
    "Mid-morning snack": ["1 fruit + 10 almonds", "Roasted chana (30 g) + coconut water"],
    "Lunch": [
        "2 rotis + dal + seasonal sabzi + salad",
        "Brown rice + rajma + salad",
        "Quinoa pulao with vegetables + chana",
    ],
    "Evening snack": ["Sprouts chaat with lemon", "Roasted makhana (no ghee) + green tea"],
    "Dinner": [
        "Tofu stir-fry with vegetables + 1 roti",
        "Dal + vegetable khichdi + salad",
        "Soya chunk curry + 1 roti + salad",
    ],
}

_JAIN = {
    "Breakfast": [
        "Moong dal chilla (no onion/garlic) + coriander chutney + curd",
        "Oats porridge with milk, nuts and fruit",
        "Besan chilla with tomato + curd",
    ],
    "Mid-morning snack": ["1 fruit + 10 almonds", "Buttermilk + roasted chana"],
    "Lunch": [
        "2 rotis + moong dal + lauki/tinda sabzi + curd",
        "Rice + toor dal + cabbage sabzi + curd",
        "Jowar roti + chana dal + capsicum sabzi",
    ],
    "Evening snack": ["Roasted makhana", "Sprouted moong chaat (no onion)"],
    "Dinner": [
        "Paneer tikka (no onion/garlic) + 1 roti + salad",
        "Moong dal khichdi + curd",
        "Paneer and capsicum sabzi + 1 roti",
    ],
}


def _meal_options(pref: str) -> dict[str, list[str]]:
    if pref == "vegan":
        return _VEGAN
    if pref == "jain":
        return _JAIN
    options = {k: list(v) for k, v in _VEG.items()}
    if pref in {"eggetarian", "non_veg"}:
        for k, v in _EGG_EXTRA.items():
            options[k] = v + options[k]
    if pref == "non_veg":
        for k, v in _NONVEG_EXTRA.items():
            options[k] = v + options[k]
    return options


# Words that must never appear in a meal for a given preference.
_FORBIDDEN = {
    "veg": ["chicken", "mutton", "fish", "prawn", "egg", "omelette", "meat", "beef", "pork", "keema", "tuna", "salmon", "lamb", "shrimp"],
    "eggetarian": ["chicken", "mutton", "fish", "prawn", "meat", "beef", "pork", "keema", "tuna", "salmon", "lamb", "shrimp"],
    "vegan": ["chicken", "mutton", "fish", "prawn", "egg", "omelette", "meat", "beef", "pork", "keema", "tuna", "salmon", "lamb", "shrimp",
              "paneer", "milk", "curd", "dahi", "ghee", "butter", "cheese", "yogurt", "yoghurt", "whey", "honey", "buttermilk", "raita", "lassi", "cream"],
    "jain": ["chicken", "mutton", "fish", "prawn", "egg", "omelette", "meat", "beef", "pork", "keema", "tuna", "salmon", "lamb", "shrimp",
             "onion", "garlic", "potato", "aloo", "carrot", "beetroot", "radish", "mooli", "ginger", "sweet potato", "shakarkand", "yam", "honey"],
    "non_veg": [],
}


_PLANT_SWAPS = re.compile(
    r"\b(?:soy|almond|oat|coconut|cashew|peanut|rice)\s+(?:milk|butter|curd|yogh?urt|cream)"
)
_NEGATED = re.compile(r"\b(?:no|without)\s+[a-z/ ,&-]+?(?=\)|\+|;|\.|$)")


def violates_preference(text: str, pref: str) -> bool:
    """True if a meal description contains something the preference rules
    out. Negations ("no onion/garlic") and plant-based swaps ("soy milk",
    "peanut butter") are removed first so they don't trip the check."""
    lowered = _PLANT_SWAPS.sub(" ", _NEGATED.sub(" ", text.lower()))
    return any(
        re.search(rf"\b{re.escape(word)}(?:s|es)?\b", lowered)
        for word in _FORBIDDEN.get(pref, [])
    )


def build_diet(profile: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    pref = profile.get("diet_preference", "veg")
    options = _meal_options(pref)
    target = metrics["target_calories"]
    meals = [
        {
            "name": name,
            "time": time,
            "calories": int(round(target * share / 10) * 10),
            "options": options.get(name, [])[:3],
        }
        for name, time, share in MEAL_SPLIT
    ]
    return {
        "daily_calories": target,
        "macros": metrics["macros"],
        "hydration_l": metrics["water_l"],
        "meals": meals,
        "foods_to_favor": _favor(metrics["effective_goal"], pref),
        "foods_to_limit": [
            "Sugary drinks and packaged juices",
            "Deep-fried snacks (samosa, pakora, chips)",
            "Refined-flour bakery items",
            "Late-night heavy meals",
        ],
    }


def _favor(goal: str, pref: str) -> list[str]:
    protein = {
        "vegan": "Tofu, soya chunks, dals, chana and rajma",
        "jain": "Paneer, curd, moong, chana and toor dal",
        "veg": "Paneer, curd, dals, chana and sprouts",
        "eggetarian": "Eggs, paneer, curd and dals",
        "non_veg": "Eggs, chicken, fish, paneer and dals",
    }.get(pref, "Dals, curd and paneer")
    base = [protein, "Colourful vegetables at every main meal", "Whole grains – jowar, bajra, oats, brown rice"]
    if goal == "gain":
        base.append("Calorie-dense extras: nuts, peanut butter, bananas, ghee in moderation")
    elif goal == "lose":
        base.append("High-volume, low-calorie foods – salads, soups, sprouts")
    else:
        base.append("Seasonal fruit and a handful of nuts daily")
    return base


# ------------------------------------------------------------------ assembly
MIND_BODY = [
    "Even a 10-minute walk measurably lifts mood – on low days, aim for 'something' rather than 'the full session'.",
    "Exercise earlier in the day tends to improve sleep that night; avoid intense training in the last 2 hours before bed.",
    "Track how you feel after each session in the Mood Tracker – most people notice the pattern within two weeks.",
    "Progress isn't linear. A missed day is data, not failure – just pick up with the next scheduled session.",
]


def rule_based_plan(profile: dict[str, Any], metrics: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    goal = metrics["effective_goal"]
    tips = [
        f"Aim for about {metrics['macros']['protein_g']} g protein a day, spread across meals.",
        f"Drink roughly {metrics['water_l']} L of water daily, more on training days.",
        "Sleep 7–9 hours – recovery drives results as much as training does.",
    ]
    if context.get("low_energy"):
        tips.insert(0, "Your recent energy has been low – it's fine to drop one set per exercise this week.")
    if context.get("short_sleep"):
        tips.insert(0, "Your last logged sleep was short. Keep today's intensity moderate.")

    return {
        "summary": (
            f"A {profile.get('days_per_week', 3)}-day {metrics['goal_label'].lower()} plan for "
            f"{profile.get('experience', 'beginner')} level with "
            f"{ {'none': 'no equipment', 'home': 'home equipment', 'gym': 'full gym access'}.get(profile.get('equipment', 'none'), 'your equipment')}, "
            f"around {metrics['target_calories']} kcal a day."
        ),
        "workout": build_workout(profile, goal),
        "diet": build_diet(profile, metrics),
        "tips": tips,
        "mind_body": MIND_BODY,
    }


def ai_messages(profile: dict[str, Any], metrics: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    schema = {
        "summary": "2-3 sentence overview written to the user",
        "workout": {
            "schedule": [
                {
                    "day": "Monday",
                    "focus": "Full body strength",
                    "type": "strength | cardio | rest",
                    "duration_min": 40,
                    "exercises": [
                        {"name": "Goblet squats", "sets": 3, "reps": "10-12", "rest_sec": 60, "notes": "short coaching cue"}
                    ],
                }
            ],
            "warmup": ["..."],
            "cooldown": ["..."],
            "progression": "how to progress over 4 weeks",
        },
        "diet": {
            "meals": [
                {"name": "Breakfast", "time": "8:00 AM", "calories": 450, "options": ["option 1", "option 2", "option 3"]}
            ],
            "foods_to_favor": ["..."],
            "foods_to_limit": ["..."],
        },
        "tips": ["3-5 practical tips"],
        "mind_body": ["2-3 tips linking movement with mood, stress and sleep"],
    }
    pref_rules = {
        "veg": "Lacto-vegetarian: no meat, fish or eggs. Dairy is fine.",
        "eggetarian": "Vegetarian plus eggs. No meat or fish.",
        "non_veg": "Eats meat, fish and eggs.",
        "vegan": "Strictly vegan: no meat, fish, eggs, dairy (milk, curd, paneer, ghee, butter) or honey.",
        "jain": "Jain: vegetarian, no eggs, and no root vegetables – no onion, garlic, potato, carrot, beetroot, radish or ginger.",
    }
    system = (
        "You are MindWell's certified-style fitness and nutrition coach inside a mental-wellbeing app. "
        "You write safe, encouraging, practical plans. Rules:\n"
        "- Return ONLY one JSON object. No markdown, no commentary before or after.\n"
        "- The schedule must contain exactly 7 entries, Monday to Sunday, with exactly "
        f"{profile.get('days_per_week', 3)} training days; the rest are type 'rest' with light recovery.\n"
        "- Only use exercises possible with the stated equipment. Respect every injury or limitation – avoid movements that load it.\n"
        f"- Diet rule: {pref_rules.get(profile.get('diet_preference', 'veg'))}\n"
        f"- Meal calories across the day must add up to about {metrics['target_calories']} kcal. "
        "Never suggest crash diets, meal skipping, fasting protocols, detoxes, fat burners or supplements beyond basic protein.\n"
        "- Prefer affordable Indian home-style foods unless the cuisine preference says otherwise. Give portions in household measures.\n"
        "- Tone: warm and non-judgemental. Never comment on appearance. Focus on strength, energy and health.\n"
        "- Match this JSON shape exactly:\n" + json.dumps(schema)
    )
    user = {
        "profile": {
            "age": profile.get("age"),
            "sex": profile.get("sex"),
            "height_cm": profile.get("height_cm"),
            "weight_kg": profile.get("weight_kg"),
            "activity_level": metrics["activity_label"],
            "goal": metrics["goal_label"],
            "experience": profile.get("experience"),
            "equipment": profile.get("equipment"),
            "days_per_week": profile.get("days_per_week"),
            "session_minutes": profile.get("session_minutes"),
            "diet_preference": profile.get("diet_preference"),
            "cuisine": profile.get("cuisine") or "Indian",
            "injuries_or_limitations": profile.get("injuries") or "none",
        },
        "numbers_already_decided": {
            "bmi": metrics["bmi"],
            "bmi_category": metrics["bmi_category"],
            "daily_calories": metrics["target_calories"],
            "protein_g": metrics["macros"]["protein_g"],
            "carbs_g": metrics["macros"]["carbs_g"],
            "fat_g": metrics["macros"]["fat_g"],
            "water_l": metrics["water_l"],
        },
        "wellbeing_context": {
            "recent_energy_low": bool(context.get("low_energy")),
            "last_sleep_short": bool(context.get("short_sleep")),
        },
    }
    language = context.get("language_name")
    if language and language != "English":
        system += f"\n- Write every string VALUE in {language}. Keep JSON keys and the 'day' and 'type' values in English."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Create my weekly plan.\n" + json.dumps(user)},
    ]


def extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    blob = cleaned[start : end + 1]
    for candidate in (blob, re.sub(r",\s*([}\]])", r"\1", blob)):
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            continue
    return None


# ---------------------------------------------------------------- normalise
def _str(value: Any, limit: int) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def _int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        number = int(float(str(value).split("-")[0]))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def _str_list(value: Any, fallback: list[str], limit: int = 8, size: int = 200) -> list[str]:
    if not isinstance(value, list):
        return fallback
    items = [_str(v, size) for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
    return items[:limit] or fallback


def _normalise_day(raw: Any, day: str, fallback_day: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback_day
    kind = _str(raw.get("type"), 20).lower()
    kind = kind if kind in {"strength", "cardio", "rest", "mobility"} else "strength"
    exercises = []
    for ex in raw.get("exercises") or []:
        if not isinstance(ex, dict) or not _str(ex.get("name"), 80):
            continue
        exercises.append(
            {
                "name": _str(ex.get("name"), 80),
                "sets": _int(ex.get("sets"), 3, 1, 10),
                "reps": _str(ex.get("reps", "10-12"), 30) or "10-12",
                "rest_sec": _int(ex.get("rest_sec"), 60, 0, 300),
                "notes": _str(ex.get("notes"), 160),
            }
        )
    if not exercises and kind != "rest":
        return fallback_day
    if not exercises:
        exercises = fallback_day["exercises"]
    return {
        "day": day,
        "focus": _str(raw.get("focus"), 80) or fallback_day["focus"],
        "type": kind,
        "duration_min": _int(raw.get("duration_min"), fallback_day["duration_min"], 5, 180),
        "exercises": exercises[:10],
    }


def normalise_plan(
    raw: dict[str, Any] | None,
    fallback: dict[str, Any],
    profile: dict[str, Any],
    metrics: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Return (plan, list of sections that had to be filled from fallback)."""
    if not isinstance(raw, dict):
        return fallback, ["all"]

    patched: list[str] = []
    plan: dict[str, Any] = {}
    plan["summary"] = _str(raw.get("summary"), 600) or fallback["summary"]

    # ---- workout
    fw = fallback["workout"]
    rw = raw.get("workout") if isinstance(raw.get("workout"), dict) else {}
    raw_days = rw.get("schedule") if isinstance(rw.get("schedule"), list) else []
    by_name = {}
    for entry in raw_days:
        if isinstance(entry, dict):
            name = _str(entry.get("day"), 12).capitalize()
            if name in WEEKDAYS and name not in by_name:
                by_name[name] = entry
    if len(by_name) < 5:
        schedule = fw["schedule"]
        patched.append("workout")
    else:
        schedule = [
            _normalise_day(by_name.get(day), day, fw["schedule"][i])
            for i, day in enumerate(WEEKDAYS)
        ]
        # Hold the AI to the number of training days the user asked for.
        training = sum(1 for d in schedule if d["type"] != "rest")
        wanted = int(profile.get("days_per_week", 3))
        if abs(training - wanted) > 1:
            schedule = fw["schedule"]
            patched.append("workout")
    plan["workout"] = {
        "schedule": schedule,
        "warmup": _str_list(rw.get("warmup"), fw["warmup"]),
        "cooldown": _str_list(rw.get("cooldown"), fw["cooldown"]),
        "progression": _str(rw.get("progression"), 800) or fw["progression"],
        "avoided_for_injury": fw.get("avoided_for_injury", False),
    }

    # ---- diet
    fd = fallback["diet"]
    rd = raw.get("diet") if isinstance(raw.get("diet"), dict) else {}
    pref = profile.get("diet_preference", "veg")
    meals = []
    dropped = 0
    for meal in rd.get("meals") or []:
        if not isinstance(meal, dict) or not _str(meal.get("name"), 40):
            continue
        options = meal.get("options") or meal.get("items") or []
        options = [_str(o, 160) for o in options if isinstance(o, str) and o.strip()]
        kept = [o for o in options if not violates_preference(o, pref)]
        dropped += len(options) - len(kept)
        if not kept:
            continue
        meals.append(
            {
                "name": _str(meal.get("name"), 40),
                "time": _str(meal.get("time"), 20),
                "calories": _int(meal.get("calories"), 0, 0, 2000),
                "options": kept[:4],
            }
        )
    if len(meals) < 3:
        meals = fd["meals"]
        patched.append("diet")
    else:
        _rescale_meals(meals, metrics["target_calories"])
    if dropped:
        patched.append(f"removed {dropped} meal option(s) that didn't match your diet preference")

    plan["diet"] = {
        "daily_calories": metrics["target_calories"],
        "macros": metrics["macros"],
        "hydration_l": metrics["water_l"],
        "meals": meals[:7],
        "foods_to_favor": [f for f in _str_list(rd.get("foods_to_favor"), fd["foods_to_favor"]) if not violates_preference(f, pref)] or fd["foods_to_favor"],
        "foods_to_limit": _str_list(rd.get("foods_to_limit"), fd["foods_to_limit"]),
    }
    plan["tips"] = _str_list(raw.get("tips"), fallback["tips"], limit=6)
    plan["mind_body"] = _str_list(raw.get("mind_body"), fallback["mind_body"], limit=4)
    return plan, patched


def _rescale_meals(meals: list[dict[str, Any]], target: int) -> None:
    """Make meal calories add up to the deterministic target."""
    total = sum(m["calories"] for m in meals)
    if total <= 0:
        share = target / len(meals)
        for m in meals:
            m["calories"] = int(round(share / 10) * 10)
        return
    factor = target / total
    for m in meals:
        m["calories"] = int(round(m["calories"] * factor / 10) * 10)
