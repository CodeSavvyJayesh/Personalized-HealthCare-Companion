"""Fail loudly if the sentiment model does not actually work.

    python scripts/verify_sentiment.py

Run during the Docker build. Sentiment is allowed to degrade at runtime, but
a deploy that ships with it silently broken would report every message as
NEUTRAL and quietly flatten every mood chart — so the build refuses instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# config.py insists on these; the values are irrelevant to this check.
os.environ.setdefault("MONGO_URI", "mongodb://build-time-check")
os.environ.setdefault("JWT_SECRET", "build-time-check-not-a-real-secret-0000")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sentiment  # noqa: E402

CASES = [
    ("I love this, it made my whole day so much better", "POSITIVE"),
    ("This is wonderful news and I feel great", "POSITIVE"),
    ("I feel terrible and everything is going wrong", "NEGATIVE"),
    ("That was an awful, miserable experience", "NEGATIVE"),
]


def main() -> int:
    backend = sentiment.load_model()
    print(f"backend: {backend}")
    failures = 0
    for text, expected in CASES:
        label, score = sentiment.classify(text)
        ok = label == expected
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {label:<8} {score:.3f}  {text}")
    if failures:
        print(f"{failures} sentiment check(s) failed", file=sys.stderr)
        return 1
    print("sentiment model verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
