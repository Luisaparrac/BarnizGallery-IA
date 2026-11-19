"""Requests-per-minute limit per (API key, client IP).

A sliding window of 60 seconds kept in memory. The service runs as a single process on
Render, so an in-memory limiter is enough; it resets when the service restarts.
The key is never stored: only a short SHA-256 prefix identifies it.
"""

import hashlib
import math
import threading
import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0
#: Above this many tracked clients, idle ones are pruned on the next call.
MAX_TRACKED_CLIENTS = 10_000


def client_identity(api_key: str | None, client_ip: str) -> str:
    """Bucket name for a key and an IP, without keeping the key itself."""
    digest = hashlib.sha256((api_key or "").encode()).hexdigest()[:16]
    return f"{digest}:{client_ip}"


class SlidingWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, identity: str, limit: int) -> int | None:
        """Register a request. Return ``None`` if allowed, else the seconds to wait."""
        now = self._clock()
        with self._lock:
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                self._prune(now)
            hits = self._hits.setdefault(identity, deque())
            while hits and now - hits[0] >= WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, math.ceil(WINDOW_SECONDS - (now - hits[0])))
            hits.append(now)
            return None

    def _prune(self, now: float) -> None:
        idle = [
            key
            for key, hits in self._hits.items()
            if not hits or now - hits[-1] >= WINDOW_SECONDS
        ]
        for key in idle:
            del self._hits[key]
