"""Safety Lab API — makes the safety layer inspectable instead of invisible.

Three endpoints:

* `GET  /safety/benchmark`      the measured benchmark report
* `POST /safety/classify`       classify a message live, without storing it
* `GET  /safety/events/summary` the caller's own escalation history

`/safety/classify` deliberately does NOT persist the text, does not call the
LLM, and does not write a safety event. It exists so the classifier can be
demonstrated and probed — including by the person who built it — without
polluting the audit trail with test data or storing a message someone typed
purely to see what happened.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends

import safety
from auth import get_current_user, utcnow
from config import settings
from db import safety_events_collection
from ratelimit import limit
from schemas import ClassifyIn

router = APIRouter(prefix="/safety", tags=["safety"])

RESULTS = Path(__file__).parent / "evals" / "results.json"
THRESHOLDS = Path(__file__).parent / "evals" / "thresholds.json"

classify_limit = limit("classify", 60, 60)


TIER_INFO = {
    "NONE": {
        "label": "No risk signal",
        "description": "Ordinary conversation. Normal model path.",
        "action": "Model responds normally.",
    },
    "DISTRESS": {
        "label": "Distress",
        "description": "Real emotional pain, no risk language.",
        "action": "Model responds normally. Event logged.",
    },
    "IDEATION": {
        "label": "Ideation",
        "description": "Thoughts of death or self-harm, no plan or means.",
        "action": "Model runs under a restricted safety prompt. Helplines appended.",
    },
    "IMMINENT": {
        "label": "Imminent risk",
        "description": "A plan, means, timeframe, or goodbye framing.",
        "action": "Model is BYPASSED. Fixed reviewed response with helplines.",
    },
}

CONTEXT_INFO = {
    "direct": "The user is speaking about themselves.",
    "academic": "Coursework, journalism or research — flag cleared.",
    "third_party": "Someone else is at risk — capped, resources still shown.",
    "past": "A resolved past experience — de-escalated to distress.",
    "fiction": "Fiction framing — de-escalated one step, never from Tier 3.",
}


@router.get("/benchmark")
def benchmark(_: str = Depends(get_current_user)) -> dict:
    """The measured benchmark. Returns `available: false` rather than
    fabricating numbers when the eval has not been run."""
    if not RESULTS.exists():
        return {
            "available": False,
            "message": "No benchmark yet. Run: python evals/scorer.py",
        }

    report = json.loads(RESULTS.read_text(encoding="utf-8"))
    thresholds = (
        json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        if THRESHOLDS.exists()
        else {}
    )

    # The full error list can be long and is not needed by the dashboard;
    # send the critical misses only, which is what anyone actually reads.
    critical = [e for e in report.get("errors", []) if e["severity"] == "critical"]

    return {
        "available": True,
        "dataset": report["dataset"],
        "headline": report["headline"],
        "per_tier": report["per_tier"],
        "confusion_matrix": report["confusion_matrix"],
        "per_category": report["per_category"],
        "latency_ms": report["latency_ms"],
        "splits": report.get("splits", {}),
        "generalisation_gap": report.get("generalisation_gap"),
        "thresholds": thresholds,
        "critical_misses": critical,
        "error_counts": {
            "critical": len(critical),
            "under_escalation": sum(
                1 for e in report.get("errors", [])
                if e["severity"] == "under_escalation"
            ),
            "over_escalation": sum(
                1 for e in report.get("errors", [])
                if e["severity"] == "over_escalation"
            ),
        },
    }


@router.get("/taxonomy")
def taxonomy(_: str = Depends(get_current_user)) -> dict:
    return {
        "tiers": [
            {"tier": tier.value, "name": tier.name, **TIER_INFO[tier.name]}
            for tier in safety.RiskTier
        ],
        "contexts": CONTEXT_INFO,
        "region": settings.CRISIS_REGION,
        "helplines": safety.HELPLINES.get(
            settings.CRISIS_REGION.upper(), safety.HELPLINES["INTL"]
        ),
        "pattern_counts": {
            "imminent": len(safety._IMMINENT),
            "ideation": len(safety._IDEATION),
            "distress": len(safety._DISTRESS),
            "academic_context": len(safety._ACADEMIC),
            "third_party_context": len(safety._THIRD_PARTY_SUBJECT),
            "fiction_context": len(safety._FICTION),
        },
    }


@router.post("/classify", dependencies=[Depends(classify_limit)])
def classify(payload: ClassifyIn, _: str = Depends(get_current_user)) -> dict:
    """Classify a message without storing it, calling the LLM, or logging
    a safety event. Inspection tool, not a chat turn."""
    import time

    start = time.perf_counter()
    assessment = safety.assess_risk(payload.text)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return {
        "tier": assessment.tier.value,
        "tier_name": assessment.tier.name,
        "raw_tier_name": assessment.raw_tier.name,
        "downgraded": assessment.downgraded,
        "context": assessment.context,
        "context_explanation": CONTEXT_INFO.get(assessment.context, ""),
        "blocks_llm": assessment.blocks_llm,
        "needs_resources": assessment.needs_resources,
        "matched_patterns": assessment.matched,
        "match_count": len(assessment.matched),
        "latency_ms": round(elapsed_ms, 4),
        "tier_info": TIER_INFO[assessment.tier.name],
        # What the user would actually have received.
        "preview": (
            safety.crisis_response(settings.CRISIS_REGION)
            if assessment.blocks_llm
            else None
        ),
        "stored": False,
    }


@router.get("/events/summary")
def events_summary(current_user: str = Depends(get_current_user)) -> dict:
    """The caller's own escalation history. Scoped to them like everything
    else — one user cannot see another's safety events."""
    since = utcnow() - timedelta(days=30)
    events = list(
        safety_events_collection.find(
            {"user_id": current_user, "created_at": {"$gte": since}}
        ).sort("created_at", -1).limit(200)
    )

    by_tier: dict[str, int] = {}
    by_action: dict[str, int] = {}
    timeline = []
    for event in events:
        tier = event.get("tier_name", "UNKNOWN")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        action = event.get("action", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
        timeline.append(
            {
                "tier_name": tier,
                "action": action,
                "context": event.get("context", "direct"),
                "created_at": event["created_at"].isoformat(),
                "message_length": event.get("message_length"),
            }
        )

    return {
        "window_days": 30,
        "total": len(events),
        "by_tier": by_tier,
        "by_action": by_action,
        "timeline": timeline[:50],
        "note": (
            "Message bodies are never stored in the audit trail — only the "
            "tier, the matched pattern names and the message length."
        ),
    }
