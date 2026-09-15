"""Sliding-window rate limiter.

In-process, which is correct for a single instance and honest about its
limit: behind more than one worker you would move `_hits` into Redis and
keep this exact interface. Noted here rather than pretended away.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _client_key(request: Request, scope: str) -> str:
    # X-Forwarded-For first, so a reverse proxy does not collapse every user
    # into one bucket.
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    return f"{scope}:{ip}"


def limit(scope: str, max_calls: int, window_seconds: int):
    """Dependency factory: `Depends(limit("chat", 30, 60))`."""

    def dependency(request: Request) -> None:
        key = _client_key(request, scope)
        now = time.time()
        with _lock:
            bucket = _hits[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= max_calls:
                retry_after = int(window_seconds - (now - bucket[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

    return dependency
