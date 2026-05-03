"""
In-memory sliding-window rate limiter for the CustomerSupport MCP Server.

Limits the number of requests per key (customer_id, IP, or any string)
within a rolling time window to protect upstream LLM API quotas and
prevent abuse.

Thread Safety
-------------
All internal state is protected by a ``threading.Lock``, making the
limiter safe for use across concurrent coroutines and threads.

Usage
-----
    from core.rate_limiter import rate_limiter

    if not rate_limiter.is_allowed(customer_id):
        raise RuntimeError("Rate limit exceeded. Please wait before retrying.")
"""

import threading
import time
from collections import defaultdict

from config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Tracks timestamps of recent requests per key and evicts expired
    entries on every access, keeping memory usage proportional to
    active keys only.
    """

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._lock = threading.Lock()
        # Maps key → list of request timestamps (monotonic)
        self._calls: dict[str, list[float]] = defaultdict(list)

    # ── Public API ────────────────────────────────────────────────────────────

    def is_allowed(self, key: str) -> bool:
        """Return ``True`` if the key is within its rate limit, ``False`` otherwise.

        Recording the request timestamp is part of this call, so callers
        should **not** call ``is_allowed`` speculatively and record separately.

        Args:
            key: Identifier to rate-limit (e.g. customer_id, IP address).
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            # Evict timestamps that have fallen outside the sliding window
            self._calls[key] = [t for t in self._calls[key] if t > cutoff]
            if len(self._calls[key]) >= self._max_requests:
                return False
            self._calls[key].append(now)
            return True

    def remaining(self, key: str) -> int:
        """Return how many requests the key has left in the current window.

        This is a read-only check – it does **not** consume a request slot.

        Args:
            key: Identifier to inspect.
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            valid = [t for t in self._calls[key] if t > cutoff]
            return max(0, self._max_requests - len(valid))

    def reset(self, key: str) -> None:
        """Clear all recorded timestamps for ``key``.

        Primarily useful in tests to restore a clean state between cases.

        Args:
            key: Identifier to reset.
        """
        with self._lock:
            self._calls.pop(key, None)

    def reset_all(self) -> None:
        """Clear all rate-limit state.  Use with caution in production."""
        with self._lock:
            self._calls.clear()

    @property
    def max_requests(self) -> int:
        """Maximum requests allowed per window."""
        return self._max_requests

    @property
    def window_seconds(self) -> int:
        """Length of the sliding window in seconds."""
        return self._window


# ── Module-level singleton ────────────────────────────────────────────────────
# Import this in tools/middleware that need rate limiting.
rate_limiter = RateLimiter()
