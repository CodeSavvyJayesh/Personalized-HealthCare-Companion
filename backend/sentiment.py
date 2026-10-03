"""Three-class sentiment on top of a two-class model.

The bundled DistilBERT head is fine-tuned on SST-2, which has exactly two
labels: POSITIVE and NEGATIVE. It is structurally incapable of returning
NEUTRAL. The dashboard nonetheless counted and charted a neutral bucket,
so that bucket was always zero and `mood_score` was pulled toward the
extremes by messages the model was barely confident about.

Fix: treat low-confidence predictions as NEUTRAL. If the model is only 62%
sure a sentence is positive, it is not telling us the sentence is positive
— it is telling us it cannot separate it. That is what neutral means here.

Two interchangeable backends run the same model:

    onnx   ONNX Runtime + a pure-Python WordPiece tokenizer. ~70 MB model,
           ~150 MB of RAM, no torch. This is what production uses.
    torch  transformers pipeline over the local safetensors weights. Handy
           on a development machine that already has torch installed.

`SENTIMENT_BACKEND=auto` (the default) picks onnx when `model.onnx` is
present and falls back to torch, so nothing changes locally until the ONNX
file is fetched with `python scripts/fetch_sentiment_model.py`.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Callable, Literal

from config import settings

log = logging.getLogger(__name__)

Label = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]

# (label, confidence) for one piece of text, straight from the model.
_Predict = Callable[[str], "tuple[str, float]"]

_predict: _Predict | None = None
_backend: str = "unloaded"
_load_error: str | None = None
_lock = threading.Lock()

MAX_TOKENS = 256


def _model_dir() -> Path:
    return Path(settings.SENTIMENT_MODEL_PATH)


def _onnx_path() -> Path:
    return _model_dir() / settings.SENTIMENT_ONNX_FILE


# ------------------------------------------------------------------ onnx
def _load_onnx() -> _Predict:
    import numpy as np
    import onnxruntime as ort

    from wordpiece import WordPieceTokenizer

    model_path = _onnx_path()
    if not model_path.exists():
        raise FileNotFoundError(
            f"{model_path} not found. Run: python scripts/fetch_sentiment_model.py"
        )

    tokenizer = WordPieceTokenizer(_model_dir() / "vocab.txt")

    labels = {0: "NEGATIVE", 1: "POSITIVE"}
    config_path = _model_dir() / "config.json"
    if config_path.exists():
        id2label = json.loads(config_path.read_text(encoding="utf-8")).get("id2label")
        if id2label:
            labels = {int(k): str(v).upper() for k, v in id2label.items()}

    options = ort.SessionOptions()
    # One request is one short sentence; extra threads only cost memory on a
    # small instance.
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
    )
    input_names = [i.name for i in session.get_inputs()]

    def predict(text: str) -> tuple[str, float]:
        ids = tokenizer.encode(text, max_length=MAX_TOKENS)
        feed = {}
        for name in input_names:
            if name == "input_ids":
                feed[name] = np.asarray([ids], dtype=np.int64)
            elif name == "attention_mask":
                feed[name] = np.ones((1, len(ids)), dtype=np.int64)
            else:  # token_type_ids on exports that still ask for it
                feed[name] = np.zeros((1, len(ids)), dtype=np.int64)
        logits = session.run(None, feed)[0][0]
        return _softmax_top([float(x) for x in logits], labels)

    return predict


def _softmax_top(logits: list[float], labels: dict[int, str]) -> tuple[str, float]:
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    total = sum(exps)
    best = max(range(len(exps)), key=exps.__getitem__)
    return labels.get(best, "NEUTRAL"), exps[best] / total


# ----------------------------------------------------------------- torch
def _load_torch() -> _Predict:
    from transformers import pipeline as hf_pipeline

    pipe = hf_pipeline(
        "sentiment-analysis",
        model=str(_model_dir()),
        local_files_only=True,
    )

    def predict(text: str) -> tuple[str, float]:
        result = pipe(text[:2000], truncation=True, max_length=MAX_TOKENS)[0]
        return str(result["label"]).upper(), float(result["score"])

    return predict


# ---------------------------------------------------------------- loading
def load_model() -> str:
    """Load the configured backend once. Returns the backend name.

    Raises when nothing can be loaded; callers that must not fail (the chat
    path) go through `classify`, which never raises.
    """
    global _predict, _backend, _load_error
    with _lock:
        if _predict is not None or _backend == "off":
            return _backend

        wanted = settings.SENTIMENT_BACKEND
        if wanted == "off":
            _backend = "off"
            return _backend

        order = {
            "auto": ["onnx", "torch"] if _onnx_path().exists() else ["torch", "onnx"],
            "onnx": ["onnx"],
            "torch": ["torch"],
        }.get(wanted, ["onnx", "torch"])

        errors = []
        for name in order:
            try:
                _predict = _load_onnx() if name == "onnx" else _load_torch()
                _backend = name
                _load_error = None
                log.info("Sentiment model loaded (backend=%s)", name)
                return _backend
            except Exception as exc:  # try the next backend
                errors.append(f"{name}: {exc}")

        _backend = "unavailable"
        _load_error = "; ".join(errors)
        raise RuntimeError(f"No sentiment backend could be loaded ({_load_error})")


def status() -> dict:
    """For /health: is sentiment real, or silently degraded to NEUTRAL?"""
    return {"backend": _backend, "ready": _predict is not None, "error": _load_error}


def classify(text: str) -> tuple[Label, float]:
    """Returns (label, confidence). Never raises — sentiment is a nice-to-have
    and must not be able to fail a chat request."""
    if not text or not text.strip():
        return "NEUTRAL", 0.0
    try:
        if _predict is None:
            if _backend in ("off", "unavailable"):
                return "NEUTRAL", 0.0
            load_model()
        label, score = _predict(text)  # type: ignore[misc]
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
