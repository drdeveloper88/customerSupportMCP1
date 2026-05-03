"""Gateway middleware for the CustomerSupport MCP Server.

Provides:
- Per-customer rate limiting via :class:`core.rate_limiter.RateLimiter`
- Prompt injection detection (OWASP LLM Top 10 – LLM01)
- Structured request / response logging
- A reusable ``@gateway`` decorator that wraps any async tool coroutine

Usage
-----
    from gateway.middleware import gateway

    @mcp.tool()
    @gateway(key_arg="customer_id")
    async def handle_customer_request(customer_id: str, message: str) -> str:
        ...
"""

import functools
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any

from core.rate_limiter import rate_limiter
from config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS

logger = logging.getLogger(__name__)

# ── Prompt injection guard ────────────────────────────────────────────────────
# Detects common prompt-injection / jailbreak attempts (OWASP LLM01).
# The pattern is intentionally broad: false positives are safe (they just block
# the request) while false negatives would let injected instructions reach the
# LLM.  Legitimate customer queries do not contain these phrases.
_INJECTION_RE = re.compile(
    r"(ignore\s+(previous|prior|above|all)\s+(instructions?|prompts?|context)|"
    r"forget\s+(everything|all|prior|previous)|"
    r"you\s+are\s+now\s+(?!a\s+customer)|"  # allow "you are now a customer"
    r"\bact\s+as\s+(a\s+)?(?!support|agent|assistant)|"
    r"\bjailbreak\b|"
    r"\bDAN\s+mode\b|"
    r"\bdeveloper\s+mode\b|"
    r"pretend\s+(you\s+are|to\s+be)\s+(?!.*support)|"
    r"override\s+your\s+(instructions?|rules?|guidelines?)|"
    r"new\s+instruction[s:]|"
    r"system\s*:\s*you\s+are)",
    re.IGNORECASE,
)


def _check_injection(text: str) -> bool:
    """Return True if *text* appears to contain a prompt injection attempt."""
    return bool(_INJECTION_RE.search(text))


class RateLimitExceeded(Exception):
    """Raised when a caller exceeds the configured request rate."""

    def __init__(self, key: str, remaining: int = 0) -> None:
        self.key = key
        self.remaining = remaining
        super().__init__(
            f"Rate limit exceeded for '{key}'. "
            f"Maximum {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS}s window."
        )


def gateway(key_arg: str = "customer_id") -> Callable:
    """Decorator factory that wraps an async tool with rate limiting and logging.

    Args:
        key_arg: Name of the function argument used as the rate-limit key.
                 Defaults to ``"customer_id"``.

    Returns:
        A decorator that wraps the coroutine function.

    Example::

        @gateway(key_arg="customer_id")
        async def handle_customer_request(customer_id: str, message: str) -> str:
            ...
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, str]]) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            # Resolve the rate-limit key from positional or keyword args
            key = kwargs.get(key_arg)
            if key is None:
                # Try positional – inspect the wrapped function's signature
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters)
                if key_arg in params:
                    idx = params.index(key_arg)
                    key = args[idx] if idx < len(args) else "unknown"
                else:
                    key = "unknown"

            logger.debug("Gateway: %s called for key=%s", func.__name__, key)

            # ── Prompt injection guard ────────────────────────────────────────
            # Check all string arguments for injection patterns
            all_text = " ".join(
                str(v) for v in list(args) + list(kwargs.values()) if isinstance(v, str)
            )
            if _check_injection(all_text):
                logger.warning(
                    "Potential prompt injection detected for key=%s on tool=%s",
                    key, func.__name__,
                )
                return (
                    "Your request contains content that cannot be processed. "
                    "Please rephrase and try again."
                )

            # ── Rate limit check ──────────────────────────────────────────────
            if not rate_limiter.is_allowed(str(key)):
                remaining = rate_limiter.remaining(str(key))
                logger.warning(
                    "Rate limit exceeded for key=%s on tool=%s (remaining=%d)",
                    key, func.__name__, remaining,
                )
                return (
                    f"I'm sorry, but your request rate has exceeded the allowed limit "
                    f"({RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds). "
                    "Please wait a moment before trying again."
                )

            # ── Execute the tool ──────────────────────────────────────────────
            try:
                result = await func(*args, **kwargs)
                logger.debug("Gateway: %s succeeded for key=%s", func.__name__, key)
                return result
            except Exception as exc:
                logger.error(
                    "Gateway: unhandled error in %s for key=%s: %s",
                    func.__name__, key, exc, exc_info=True,
                )
                return (
                    "An unexpected error occurred while processing your request. "
                    "Please try again or contact support directly."
                )

        return wrapper

    return decorator
