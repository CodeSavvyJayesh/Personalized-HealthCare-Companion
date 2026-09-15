"""Crisis-detection benchmark scorer.

Runs the classifier over the labeled set and reports the numbers that
actually matter for this system:

* **Tier-3 recall** — of the messages that signal imminent risk, how many
  did we catch? A miss here is the worst outcome the product can produce,
  so this is the headline metric and the one CI gates on.
* **Escalation recall** — of everything that should have surfaced a
  helpline (IDEATION + IMMINENT), how much did?
* **False-positive rate on NONE** — how often does an ordinary message get
  flagged? This is the cost side of tuning recall up. Report it honestly;
  a classifier with 100% recall and a 40% false-positive rate is useless
  and a reviewer will know it.
* **Per-category breakdown** — where the misses concentrate (obfuscation?
  implicit phrasing? code-switching?) is more actionable than one number.

Usage:
    python -m evals.scorer            # from backend/
    python evals/scorer.py --json     # machine-readable only
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safety import RiskTier, assess_risk  # noqa: E402

TIERS = ["NONE", "DISTRESS", "IDEATION", "IMMINENT"]
DATASET = Path(__file__).parent / "crisis_set.jsonl"
RESULTS = Path(__file__).parent / "results.json"
THRESHOLDS = Path(__file__).parent / "thresholds.json"


def load_dataset(path: Path = DATASET) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run: python evals/build_dataset.py"
        )
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "support": tp + fn,
    }


def evaluate(rows: list[dict]) -> dict:
    confusion: dict[str, Counter] = {t: Counter() for t in TIERS}
    per_category: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "correct": 0, "misses": []}
    )
    latencies_ms: list[float] = []
    errors: list[dict] = []

    for row in rows:
        expected = row["label"]
        start = time.perf_counter()
        result = assess_risk(row["text"])
        latencies_ms.append((time.perf_counter() - start) * 1000)
        predicted = result.tier.name

        confusion[expected][predicted] += 1

        cat = per_category[row["category"]]
        cat["total"] += 1
        if predicted == expected:
            cat["correct"] += 1
        else:
            cat["misses"].append(
                {"id": row["id"], "text": row["text"],
                 "expected": expected, "predicted": predicted}
            )
            errors.append(
                {"id": row["id"], "text": row["text"], "category": row["category"],
                 "lang": row["lang"], "expected": expected, "predicted": predicted,
                 "severity": _severity(expected, predicted)}
            )

    # ---- per-tier precision / recall / f1 ----
    per_tier = {}
    for tier in TIERS:
        tp = confusion[tier][tier]
        fn = sum(v for k, v in confusion[tier].items() if k != tier)
        fp = sum(confusion[other][tier] for other in TIERS if other != tier)
        per_tier[tier] = _prf(tp, fp, fn)

    total = len(rows)
    correct = sum(confusion[t][t] for t in TIERS)

    # ---- the metrics this product lives or dies by ----
    imminent_rows = [r for r in rows if r["label"] == "IMMINENT"]
    imminent_caught = sum(
        1 for r in imminent_rows
        if assess_risk(r["text"]).tier is RiskTier.IMMINENT
    )
    tier3_recall = imminent_caught / len(imminent_rows) if imminent_rows else 0.0

    escalate_rows = [r for r in rows if r["label"] in ("IDEATION", "IMMINENT")]
    escalate_caught = sum(
        1 for r in escalate_rows
        if assess_risk(r["text"]).tier >= RiskTier.IDEATION
    )
    escalation_recall = (
        escalate_caught / len(escalate_rows) if escalate_rows else 0.0
    )

    none_rows = [r for r in rows if r["label"] == "NONE"]
    none_flagged = sum(
        1 for r in none_rows if assess_risk(r["text"]).tier > RiskTier.NONE
    )
    false_positive_rate = none_flagged / len(none_rows) if none_rows else 0.0

    # An ordinary message escalated all the way to a crisis response is a
    # much worse failure than one nudged to DISTRESS — count it separately.
    none_to_imminent = sum(
        1 for r in none_rows
        if assess_risk(r["text"]).tier is RiskTier.IMMINENT
    )

    lat = sorted(latencies_ms)

    def pct(p: float) -> float:
        return round(lat[min(int(len(lat) * p), len(lat) - 1)], 4)

    return {
        "dataset": {
            "path": DATASET.name,
            "examples": total,
            "by_label": {t: sum(confusion[t].values()) for t in TIERS},
            "by_source": dict(Counter(r.get("source", "unknown") for r in rows)),
            "languages": dict(Counter(r.get("lang", "en") for r in rows)),
        },
        "headline": {
            "tier3_recall": round(tier3_recall, 4),
            "tier3_missed": len(imminent_rows) - imminent_caught,
            "escalation_recall": round(escalation_recall, 4),
            "false_positive_rate": round(false_positive_rate, 4),
            "none_escalated_to_crisis": none_to_imminent,
            "exact_tier_accuracy": round(correct / total, 4) if total else 0.0,
        },
        "per_tier": per_tier,
        "confusion_matrix": {
            expected: {pred: confusion[expected][pred] for pred in TIERS}
            for expected in TIERS
        },
        "per_category": {
            name: {
                "total": v["total"],
                "correct": v["correct"],
                "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else 0,
            }
            for name, v in sorted(per_category.items())
        },
        "latency_ms": {
            "mean": round(statistics.fmean(lat), 4),
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "max": round(lat[-1], 4),
        },
        "errors": errors,
    }


def _severity(expected: str, predicted: str) -> str:
    """How bad is this particular mistake?"""
    rank = {t: i for i, t in enumerate(TIERS)}
    if expected == "IMMINENT" and predicted != "IMMINENT":
        return "critical"          # missed a life-threatening message
    if rank[predicted] < rank[expected]:
        return "under_escalation"  # under-reacted
    return "over_escalation"       # over-reacted; annoying, not dangerous


def render(report: dict) -> str:
    h = report["headline"]
    lines = [
        "",
        "=" * 66,
        "  MindWell — Crisis Detection Benchmark",
        "=" * 66,
        f"  Examples          {report['dataset']['examples']}",
        f"  Languages         {', '.join(report['dataset']['languages'])}",
        "",
        "  HEADLINE",
        f"    Tier-3 recall (imminent risk caught)   {h['tier3_recall']:.1%}",
        f"    Imminent-risk messages missed          {h['tier3_missed']}",
        f"    Escalation recall (helpline shown)     {h['escalation_recall']:.1%}",
        f"    False-positive rate on ordinary msgs   {h['false_positive_rate']:.1%}",
        f"    Ordinary msgs escalated to crisis      {h['none_escalated_to_crisis']}",
        f"    Exact tier accuracy                    {h['exact_tier_accuracy']:.1%}",
        "",
        "  PER TIER",
        f"    {'tier':<10}{'precision':>11}{'recall':>9}{'f1':>8}{'n':>6}",
    ]
    for tier, m in report["per_tier"].items():
        lines.append(
            f"    {tier:<10}{m['precision']:>11.3f}{m['recall']:>9.3f}"
            f"{m['f1']:>8.3f}{m['support']:>6}"
        )

    lines += ["", "  CONFUSION MATRIX  (rows = true, cols = predicted)",
              f"    {'':<10}" + "".join(f"{t[:4]:>10}" for t in TIERS)]
    for expected, preds in report["confusion_matrix"].items():
        lines.append(
            f"    {expected:<10}" + "".join(f"{preds[t]:>10}" for t in TIERS)
        )

    lines += ["", "  BY CATEGORY"]
    for name, m in report["per_category"].items():
        flag = "  <-- weak" if m["accuracy"] < 0.8 else ""
        lines.append(
            f"    {name:<24}{m['correct']:>4}/{m['total']:<4}"
            f"{m['accuracy']:>8.1%}{flag}"
        )

    if report.get("splits"):
        lines += ["", "  BY SPLIT  (holdout is the number to quote)",
                  f"    {'split':<10}{'n':>6}{'tier3 recall':>15}{'accuracy':>11}{'FPR':>8}"]
        for name, sp in report["splits"].items():
            h = sp["headline"]
            lines.append(
                f"    {name:<10}{sp['examples']:>6}{h['tier3_recall']:>14.1%}"
                f"{h['exact_tier_accuracy']:>11.1%}{h['false_positive_rate']:>8.1%}"
            )
        gap = report.get("generalisation_gap")
        if gap:
            lines.append(
                f"    generalisation gap (dev - holdout): "
                f"tier-3 recall {gap['tier3_recall']:+.1%}, "
                f"accuracy {gap['exact_tier_accuracy']:+.1%}"
            )

    lat = report["latency_ms"]
    lines += [
        "",
        f"  LATENCY  mean {lat['mean']:.3f}ms   p95 {lat['p95']:.3f}ms   "
        f"max {lat['max']:.3f}ms",
    ]

    critical = [e for e in report["errors"] if e["severity"] == "critical"]
    if critical:
        lines += ["", f"  CRITICAL MISSES ({len(critical)}) — imminent risk not caught:"]
        for e in critical[:15]:
            lines.append(f"    [{e['predicted']:<8}] {e['text'][:60]}")
        if len(critical) > 15:
            lines.append(f"    ... and {len(critical) - 15} more")

    lines += ["", "=" * 66, ""]
    return "\n".join(lines)


def evaluate_all(rows: list[dict]) -> dict:
    """Overall plus per-split.

    `holdout` is the number that should be quoted anywhere. The classifier
    is tuned against `dev`; a large dev-holdout gap means the patterns were
    fitted to the examples rather than to the phenomenon, and hiding that
    behind a single blended figure would defeat the point of the split.
    """
    report = evaluate(rows)
    report["splits"] = {}
    for split in ("dev", "holdout"):
        subset = [r for r in rows if r.get("split") == split]
        if subset:
            sub = evaluate(subset)
            report["splits"][split] = {
                "examples": len(subset),
                "headline": sub["headline"],
                "per_tier": sub["per_tier"],
            }
    dev = report["splits"].get("dev", {}).get("headline", {})
    hold = report["splits"].get("holdout", {}).get("headline", {})
    if dev and hold:
        report["generalisation_gap"] = {
            "tier3_recall": round(
                dev["tier3_recall"] - hold["tier3_recall"], 4
            ),
            "exact_tier_accuracy": round(
                dev["exact_tier_accuracy"] - hold["exact_tier_accuracy"], 4
            ),
            "note": "dev minus holdout; a large positive gap means overfitting",
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    report = evaluate_all(load_dataset())

    if not args.no_write:
        RESULTS.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render(report))
        if not args.no_write:
            print(f"  Full report written to evals/{RESULTS.name}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
