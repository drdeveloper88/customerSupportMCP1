"""Unit tests for core/rate_limiter.py"""
import time
from unittest.mock import patch

import pytest

from core.rate_limiter import RateLimiter


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def limiter():
    """Fresh limiter: 3 requests per 60-second window."""
    return RateLimiter(max_requests=3, window_seconds=60)


# ── is_allowed ────────────────────────────────────────────────────────────────

class TestIsAllowed:
    def test_allows_up_to_max_requests(self, limiter):
        for _ in range(3):
            assert limiter.is_allowed("CUST-A") is True

    def test_denies_beyond_max_requests(self, limiter):
        for _ in range(3):
            limiter.is_allowed("CUST-A")
        assert limiter.is_allowed("CUST-A") is False

    def test_different_keys_are_independent(self, limiter):
        for _ in range(3):
            limiter.is_allowed("CUST-A")
        # CUST-B should be unaffected
        assert limiter.is_allowed("CUST-B") is True

    def test_expired_timestamps_are_not_counted(self, limiter):
        """Requests older than the window should not count toward the limit."""
        past = time.monotonic() - 120  # well outside the 60 s window
        limiter._calls["CUST-C"] = [past, past, past]  # fake "old" calls
        # Should allow new request since old timestamps are outside window
        assert limiter.is_allowed("CUST-C") is True


# ── remaining ─────────────────────────────────────────────────────────────────

class TestRemaining:
    def test_full_remaining_on_fresh_key(self, limiter):
        assert limiter.remaining("CUST-NEW") == 3

    def test_remaining_decrements_after_allowed(self, limiter):
        limiter.is_allowed("CUST-D")
        assert limiter.remaining("CUST-D") == 2

    def test_remaining_is_zero_when_limit_reached(self, limiter):
        for _ in range(3):
            limiter.is_allowed("CUST-E")
        assert limiter.remaining("CUST-E") == 0

    def test_remaining_does_not_consume_a_slot(self, limiter):
        before = limiter.remaining("CUST-F")
        limiter.remaining("CUST-F")
        assert limiter.remaining("CUST-F") == before


# ── reset ─────────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_restores_full_limit(self, limiter):
        for _ in range(3):
            limiter.is_allowed("CUST-G")
        assert limiter.is_allowed("CUST-G") is False
        limiter.reset("CUST-G")
        assert limiter.is_allowed("CUST-G") is True

    def test_reset_unknown_key_is_safe(self, limiter):
        limiter.reset("CUST-UNKNOWN")  # should not raise


# ── reset_all ─────────────────────────────────────────────────────────────────

class TestResetAll:
    def test_reset_all_clears_every_key(self, limiter):
        limiter.is_allowed("CUST-H")
        limiter.is_allowed("CUST-I")
        limiter.reset_all()
        assert limiter.remaining("CUST-H") == 3
        assert limiter.remaining("CUST-I") == 3
