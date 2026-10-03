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


def _post(model: str, messages: list[dict[str, str]], temperature: float,
          max_tokens: int | None, timeout: int) -> requests.Response:
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return requests.post(
        f"{settings.LLM_BASE_URL}/chat/completions",
        json=payload,
        headers=_headers(),
        timeout=timeout,
    )


def _retry_after(response: requests.Response) -> float:
    try:
        return float(response.headers.get("retry-after", "1"))
    except ValueError:
        return 1.0


def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.8,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> str:
    """One chat completion. Raises LLMUnavailable on any failure.

    Rate limiting (HTTP 429) is handled separately from real failures. A
    hosted free tier says "slow down" routinely; treating that as the server
    being dead would trip the breaker and take chat offline for everyone for
    30 seconds over what is a one-second wait. So a 429 gets one short retry,
    then the fallback model if one is configured, and never counts toward
    the breaker.
    """
    if breaker.is_open:
        raise LLMUnavailable("LLM circuit breaker is open")

    limit = timeout or settings.LLM_TIMEOUT
    models = [settings.LLM_MODEL]
    if settings.LLM_FALLBACK_MODEL and settings.LLM_FALLBACK_MODEL != settings.LLM_MODEL:
        models.append(settings.LLM_FALLBACK_MODEL)

    last_error = "no attempt made"
    try:
        for index, model in enumerate(models):
            response = _post(model, messages, temperature, max_tokens, limit)

            if response.status_code == 429:
                wait = _retry_after(response)
                if wait <= 3 and index == len(models) - 1:
                    time.sleep(wait)
                    response = _post(model, messages, temperature, max_tokens, limit)
                if response.status_code == 429:
                    last_error = f"{model} is rate limited"
                    log.warning("LLM rate limited on %s", model)
                    continue

            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            breaker.record_success()
            return (content or "").strip()
    except Exception as exc:
        breaker.record_failure()
        log.error("LLM call failed (%s): %s", settings.LLM_BASE_URL, exc)
        raise LLMUnavailable(str(exc)) from exc

    # Every model was rate limited: unavailable for this request, but the
    # provider is up, so the breaker is left alone.
    raise LLMUnavailable(last_error)


def health() -> dict:
    return {
        "base_url": settings.LLM_BASE_URL,
        "model": settings.LLM_MODEL,
        "fallback_model": settings.LLM_FALLBACK_MODEL or None,
        "api_key_set": bool(settings.LLM_API_KEY),
        "circuit_open": breaker.is_open,
    }


def is_local() -> bool:
    return any(h in settings.LLM_BASE_URL for h in ("127.0.0.1", "localhost", "host.docker.internal"))


def warm_up() -> None:
    """Fire-and-forget warmup so the first real user does not pay for the
    model load. Only meaningful for a local model server: a hosted API has
    nothing to warm, and the call would just spend rate-limit budget."""
    if not is_local():
        return

    def _run() -> None:
        try:
            chat([{"role": "user", "content": "hi"}], max_tokens=8, timeout=30)
            log.info("LLM warmed up")
        except Exception as exc:
            log.warning("LLM warmup failed (this is not fatal): %s", exc)

    threading.Thread(target=_run, daemon=True).start()
