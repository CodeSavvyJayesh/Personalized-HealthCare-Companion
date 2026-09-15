"""Three-class sentiment on top of a two-class model.

The bundled DistilBERT head is fine-tuned on SST-2, which has exactly two
labels: POSITIVE and NEGATIVE. It is structurally incapable of returning
NEUTRAL. The dashboard nonetheless counted and charted a neutral bucket,
so that bucket was always zero and `mood_score` was pulled toward the
extremes by messages the model was barely confident about.

Fix: treat low-confidence predictions as NEUTRAL. If the model is only 62%
sure a sentence is positive, it is not telling us the sentence is positive
— it is telling us it cannot separate it. That is what neutral means here.

The threshold is configurable (SENTIMENT_NEUTRAL_THRESHOLD) so it can be
tuned against a labelled set rather than guessed at forever.
"""

from __future__ import annotations

import logging
from typing import Literal

from config import settings

log = logging.getLogger(__name__)

Label = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]

_pipeline = None


def load_model():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    from transformers import pipeline as hf_pipeline

    log.info("Loading sentiment model from %s", settings.SENTIMENT_MODEL_PATH)
    _pipeline = hf_pipeline(
        "sentiment-analysis",
        model=settings.SENTIMENT_MODEL_PATH,
        local_files_only=True,
    )
    log.info("Sentiment model loaded")
    return _pipeline


def classify(text: str) -> tuple[Label, float]:
    """Returns (label, confidence). Never raises — sentiment is a nice-to-have
    and must not be able to fail a chat request."""
    if not text or not text.strip():
        return "NEUTRAL", 0.0
    try:
        pipe = load_model()
        result = pipe(text[:512])[0]
        label = result["label"].upper()
        score = float(result["score"])
    except Exception as exc:
        log.warning("Sentiment failed, defaulting to NEUTRAL: %s", exc)
        return "NEUTRAL", 0.0

    if score < settings.SENTIMENT_NEUTRAL_THRESHOLD:
        return "NEUTRAL", score
    if label not in ("POSITIVE", "NEGATIVE"):
        return "NEUTRAL", score
    return label, score  # type: ignore[return-value]


def polarity(label: str) -> int:
    """POSITIVE -> +1, NEGATIVE -> -1, anything else -> 0."""
    return {"POSITIVE": 1, "NEGATIVE": -1}.get((label or "").upper(), 0)
