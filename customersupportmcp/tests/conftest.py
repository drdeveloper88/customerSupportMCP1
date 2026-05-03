"""
Pytest shared fixtures for the CustomerSupport MCP Server test suite.

Environment setup
-----------------
A dummy GROQ_API_KEY is set before any module imports to prevent
config.py from warning / erroring in CI where no real key exists.
Ollama is disabled by default in tests.

Database isolation
------------------
All tests run against a shared in-memory SQLite engine that is created
once per session and wiped between each test function.  This avoids the
slow cost of recreating the schema on every test while keeping tests
fully independent.
"""

import os

# Must be set BEFORE importing config.py or any module that imports it
os.environ.setdefault("GROQ_API_KEY", "test-groq-key-for-testing")
os.environ.setdefault("OLLAMA_ENABLED", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

import pytest
from sqlalchemy import create_engine, text

# ── Import after env vars are set ────────────────────────────────────────────
import data.database as db_module
import tools.ticket_tools as ticket_tools_module
import tools.order_tools as order_tools_module


# ── Session-scoped in-memory SQLite engine ────────────────────────────────────

@pytest.fixture(scope="session")
def mem_engine():
    """Create a single in-memory SQLite engine for the whole test session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    db_module.metadata.create_all(engine)
    return engine


# ── Per-test engine patching and table cleanup ────────────────────────────────

@pytest.fixture(autouse=True)
def patch_db(mem_engine, monkeypatch):
    """Redirect all database operations to the in-memory engine and clean up after each test."""
    monkeypatch.setattr(db_module, "engine", mem_engine)
    monkeypatch.setattr(ticket_tools_module, "engine", mem_engine)
    monkeypatch.setattr(order_tools_module, "engine", mem_engine)

    yield

    # Wipe all data between tests so they are fully independent
    with mem_engine.begin() as conn:
        conn.execute(text("DELETE FROM ticket_notes"))
        conn.execute(text("DELETE FROM tickets"))
        conn.execute(text("DELETE FROM refunds"))
        conn.execute(text("DELETE FROM order_items"))
        conn.execute(text("DELETE FROM orders"))


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_order(mem_engine):
    """Insert a single delivered order and return its dict."""
    from sqlalchemy import insert
    from data.database import orders_t, order_items_t, now_iso

    order_data = {
        "order_id": "ORD-9999",
        "customer_id": "CUST-001",
        "status": "delivered",
        "subtotal": 49.99,
        "shipping_cost": 5.99,
        "total": 55.98,
        "shipping_address": "1 Test Street, London, UK",
        "shipping_method": "standard",
        "created_at": now_iso(),
        "shipped_at": now_iso(),
        "delivered_at": now_iso(),
        "estimated_delivery": now_iso(),
        "cancelled_at": None,
        "cancellation_reason": None,
        "tracking_number": "TRK123456",
        "carrier": "UPS",
    }
    item_data = {
        "order_id": "ORD-9999",
        "product_id": "PROD-01",
        "name": "Test Widget",
        "quantity": 2,
        "price": 24.99,
    }
    with mem_engine.begin() as conn:
        conn.execute(insert(orders_t).values(**order_data))
        conn.execute(insert(order_items_t).values(**item_data))

    return {**order_data, "items": [item_data]}


@pytest.fixture
def sample_ticket(mem_engine):
    """Insert a single open ticket and return its dict."""
    from tools.ticket_tools import create_support_ticket
    return create_support_ticket(
        customer_id="CUST-001",
        subject="Test issue",
        description="This is a test issue description.",
        priority="medium",
    )
