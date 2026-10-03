"""Download the ONNX sentiment model into backend/models/.

    python scripts/fetch_sentiment_model.py

The weights are a 68 MB binary and do not belong in git, so the Docker build
runs this, and you run it once locally if you want the lightweight ONNX
backend instead of torch. Standard library only — it has to work in an image
that has nothing else installed yet.

The file is the int8-quantised ONNX export of
distilbert-base-uncased-finetuned-sst-2-english, the same model as the
safetensors weights this project started with.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

MODEL_DIR = Path(os.getenv("SENTIMENT_MODEL_PATH", Path(__file__).resolve().parent.parent / "models"))
TARGET = MODEL_DIR / os.getenv("SENTIMENT_ONNX_FILE", "model.onnx")

DEFAULT_URL = (
    "https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english"
    "/resolve/main/onnx/model_quantized.onnx"
)
URL = os.getenv("SENTIMENT_ONNX_URL", DEFAULT_URL)

# A truncated or HTML-error download must not be mistaken for a model.
MIN_BYTES = 20 * 1024 * 1024


# The tokenizer vocabulary is small and normally lives in git next to this
# script; fetch it only if a checkout somehow arrived without it.
VOCAB_URL = (
    "https://huggingface.co/distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    "/resolve/main/vocab.txt"
)


def download(url: str, target: Path, min_bytes: int) -> bool:
    partial = target.with_name(target.name + ".part")
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "mindwell-build"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
            done = 0
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
                done += len(chunk)
                if done % (10 * 1024 * 1024) < 1024 * 1024 and done > 1024 * 1024:
                    print(f"  {done / 1e6:.0f} MB")
    except Exception as exc:
        partial.unlink(missing_ok=True)
        print(f"FAILED to download {url}: {exc}", file=sys.stderr)
        return False

    size = partial.stat().st_size
    if size < min_bytes:
        partial.unlink(missing_ok=True)
        print(f"FAILED: {url} returned only {size} bytes", file=sys.stderr)
        return False

    partial.replace(target)
    print(f"Saved {target} ({size / 1e6:.1f} MB)")
    return True


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    vocab = MODEL_DIR / "vocab.txt"
    if not vocab.exists() and not download(VOCAB_URL, vocab, 100_000):
        return 1

    if TARGET.exists() and TARGET.stat().st_size >= MIN_BYTES and "--force" not in sys.argv:
        print(f"{TARGET} already present ({TARGET.stat().st_size / 1e6:.1f} MB)")
        return 0

    return 0 if download(URL, TARGET, MIN_BYTES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
