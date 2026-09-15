"""CI regression gate for the crisis classifier.

The point of this file: a future change to safety.py that quietly makes the
product less safe fails the build instead of shipping. Thresholds live in
evals/thresholds.json and are a ratchet — raise them when the classifier
improves; never lower one to turn a red build green.

`holdout` is the split the classifier was NOT tuned against, so it is the
gate that actually means something.
"""

import json
from pathlib import Path

import pytest

from evals.scorer import evaluate_all, load_dataset

EVALS = Path(__file__).resolve().parent.parent / "evals"


@pytest.fixture(scope="module")
def report():
    return evaluate_all(load_dataset())


@pytest.fixture(scope="module")
def thresholds():
    return json.loads((EVALS / "thresholds.json").read_text(encoding="utf-8"))


# ----------------------------------------------------- holdout (the real gate)
def test_holdout_tier3_recall(report, thresholds):
    """Missing an imminent-risk message is the worst thing this can do."""
    actual = report["splits"]["holdout"]["headline"]["tier3_recall"]
    floor = thresholds["holdout"]["min_tier3_recall"]
    assert actual >= floor, (
        f"Tier-3 recall on unseen data fell to {actual:.1%} (floor {floor:.1%}). "
        f"A change made the classifier miss more imminent-risk messages."
    )


def test_holdout_escalation_recall(report, thresholds):
    actual = report["splits"]["holdout"]["headline"]["escalation_recall"]
    assert actual >= thresholds["holdout"]["min_escalation_recall"]


def test_holdout_false_positive_rate(report, thresholds):
    """Recall bought with a flood of false alarms is not an improvement."""
    actual = report["splits"]["holdout"]["headline"]["false_positive_rate"]
    ceiling = thresholds["holdout"]["max_false_positive_rate"]
    assert actual <= ceiling, (
        f"False-positive rate rose to {actual:.1%} (ceiling {ceiling:.1%})."
    )


def test_no_ordinary_message_triggers_crisis_response(report, thresholds):
    """Showing the crisis text to someone discussing their weekend is the
    failure that destroys trust in the whole feature."""
    for split in ("holdout", "dev"):
        assert (
            report["splits"][split]["headline"]["none_escalated_to_crisis"]
            <= thresholds["holdout"]["max_none_escalated_to_crisis"]
        )


# -------------------------------------------------------------------- overall
def test_overall_tier3_recall(report, thresholds):
    actual = report["headline"]["tier3_recall"]
    assert actual >= thresholds["overall"]["min_tier3_recall"]


def test_overall_false_positive_rate(report, thresholds):
    actual = report["headline"]["false_positive_rate"]
    assert actual <= thresholds["overall"]["max_false_positive_rate"]


def test_classifier_is_fast_enough_to_run_inline(report, thresholds):
    """It runs on every message before the model does, so it has to be
    cheap enough that nobody is ever tempted to make it optional."""
    p95 = report["latency_ms"]["p95"]
    assert p95 <= thresholds["overall"]["max_p95_latency_ms"]


# ------------------------------------------------------------ dataset health
def test_dataset_has_a_holdout_split():
    rows = load_dataset()
    splits = {r.get("split") for r in rows}
    assert "holdout" in splits and "dev" in splits


def test_every_tier_is_represented_in_holdout():
    rows = [r for r in load_dataset() if r.get("split") == "holdout"]
    labels = {r["label"] for r in rows}
    assert labels == {"NONE", "DISTRESS", "IDEATION", "IMMINENT"}


def test_generalisation_gap_is_reported(report):
    """Not asserted on — a gap is information, not a failure. But it must be
    visible, because a blended score can hide overfitting completely."""
    assert "generalisation_gap" in report
