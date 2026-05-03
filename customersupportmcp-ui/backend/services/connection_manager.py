"""
WebSocket connection manager.

Tracks every active WebSocket session, collects performance counters,
and provides an application-wide singleton ``manager`` that is shared
by the chat endpoint and the metrics endpoint.
"""

import logging
import time
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe manager for active WebSocket connections.

    Usage
    -----
    From the WebSocket endpoint::

        manager.connect(customer_id, websocket)
        try:
            ...
        finally:
            manager.disconnect(customer_id, websocket)

    From the metrics endpoint::

        stats = manager.stats()
    """

    def __init__(self) -> None:
        # customer_id → list[WebSocket]
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._total_messages: int = 0
        self._total_response_ms: float = 0.0
        self._response_count: int = 0
        self._started_at: float = time.monotonic()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, customer_id: str, ws: WebSocket) -> None:
        self._connections[customer_id].append(ws)
        logger.info(
            "WS connect  customer=%s  active=%d", customer_id, self.active_count
        )

    def disconnect(self, customer_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(customer_id, [])
        try:
            conns.remove(ws)
        except ValueError:
            pass
        if not conns:
            self._connections.pop(customer_id, None)
        logger.info(
            "WS disconnect  customer=%s  active=%d", customer_id, self.active_count
        )

    # ── Metrics recording ─────────────────────────────────────────────────────

    def record_message(self, response_ms: float) -> None:
        """Record a completed AI response with its round-trip latency."""
        self._total_messages += 1
        self._total_response_ms += response_ms
        self._response_count += 1

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def active_count(self) -> int:
        return sum(len(v) for v in self._connections.values())

    @property
    def active_customers(self) -> list[str]:
        return list(self._connections.keys())

    @property
    def total_messages(self) -> int:
        return self._total_messages

    @property
    def avg_response_ms(self) -> float:
        if self._response_count == 0:
            return 0.0
        return round(self._total_response_ms / self._response_count, 1)

    @property
    def uptime_seconds(self) -> int:
        return int(time.monotonic() - self._started_at)

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return a snapshot of all current metrics."""
        return {
            "active_connections": self.active_count,
            "active_customers":   self.active_customers,
            "total_messages":     self.total_messages,
            "avg_response_ms":    self.avg_response_ms,
            "uptime_seconds":     self.uptime_seconds,
        }


# ── Application-wide singleton ────────────────────────────────────────────────
manager = ConnectionManager()
