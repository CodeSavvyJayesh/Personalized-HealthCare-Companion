"""LLM client.

Provider-agnostic: anything that speaks the OpenAI chat-completions shape
works — Ollama, vLLM, Groq, Together, OpenAI. That is the difference
between a project that runs on one laptop and one that can be deployed,
and it is a two-line change in .env rather than a code change.

Includes a circuit breaker so a dead model server degrades the app to its
rule-based fallbacks instead of making every request hang for 60 seconds.
"""

from __future__ import annotations

import logging
import threading
import time

import requests

from config import settings

log = logging.getLogger(__name__)


class CircuitBreaker:
    """Open the circuit after N consecutive failures; probe again later."""

    def __init__(self, threshold: int = 3, cooldown: int = 30) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._failures < self.threshold:
                return False
            if time.time() - self._opened_at > self.cooldown:
                self._failures = 0  # half-open: let one request through
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                self._opened_at = time.time()


breaker = CircuitBreaker()


class LLMUnavailable(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
    return headers


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.8,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> str:
    if breaker.is_open:
        raise LLMUnavailable("LLM circuit breaker is open")

    payload: dict = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    url = f"{settings.LLM_BASE_URL}/chat/completions"
    try:
        response = requests.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=timeout or settings.LLM_TIMEOUT,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        breaker.record_success()
        return content.strip()
    except Exception as exc:
        breaker.record_failure()
        log.error("LLM call failed (%s): %s", url, exc)
        raise LLMUnavailable(str(exc)) from exc


def health() -> dict:
    return {
        "base_url": settings.LLM_BASE_URL,
        "model": settings.LLM_MODEL,
        "circuit_open": breaker.is_open,
    }


def warm_up() -> None:
    """Fire-and-forget warmup so the first real user does not pay for the
    model load."""

    def _run() -> None:
        try:
            chat([{"role": "user", "content": "hi"}], max_tokens=8, timeout=30)
            log.info("LLM warmed up")
        except Exception as exc:
            log.warning("LLM warmup failed (this is not fatal): %s", exc)

    threading.Thread(target=_run, daemon=True).start()
