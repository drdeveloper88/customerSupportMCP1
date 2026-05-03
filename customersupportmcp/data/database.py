"""
SQLite real-time database layer – CustomerSupport MCP Server.

Uses SQLAlchemy Core 2.x (no ORM) for a lightweight, portable store.
Tables are created automatically on first import; seed data is loaded
from the legacy JSON files when the database is empty.

Tables
------
orders          – master order record (one row per order)
order_items     – line items linked to an order (one-to-many)
tickets         – support tickets
ticket_notes    – immutable audit / note log per ticket
refunds         – refund requests submitted via process_refund tool
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)

logger = logging.getLogger(__name__)

_SRC_DIR     = Path(__file__).resolve().parent
_DATA_DIR    = Path(os.environ.get("DATA_DIR", _SRC_DIR))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH     = _DATA_DIR / "support.db"
_ORDERS_JSON = _SRC_DIR / "mock_orders.json"

# ── Engine ────────────────────────────────────────────────────────────────────

engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

metadata = MetaData()

# ── Table definitions ─────────────────────────────────────────────────────────

orders_t = Table(
    "orders", metadata,
    Column("order_id",            String(32),  primary_key=True),
    Column("customer_id",         String(32),  nullable=False, index=True),
    Column("status",              String(20),  nullable=False),
    Column("subtotal",            Float,       nullable=False, default=0.0),
    Column("shipping_cost",       Float,       nullable=False, default=0.0),
    Column("total",               Float,       nullable=False, default=0.0),
    Column("shipping_address",    Text),
    Column("shipping_method",     String(64)),
    Column("created_at",          String(32)),
    Column("shipped_at",          String(32)),
    Column("delivered_at",        String(32)),
    Column("estimated_delivery",  String(32)),
    Column("cancelled_at",        String(32)),
    Column("cancellation_reason", Text),
    Column("tracking_number",     String(64)),
    Column("carrier",             String(32)),
)

order_items_t = Table(
    "order_items", metadata,
    Column("id",         Integer, primary_key=True, autoincrement=True),
    Column("order_id",   String(32), nullable=False, index=True),
    Column("product_id", String(32)),
    Column("name",       Text,       nullable=False),
    Column("quantity",   Integer,    nullable=False, default=1),
    Column("price",      Float,      nullable=False, default=0.0),
)

tickets_t = Table(
    "tickets", metadata,
    Column("ticket_id",         String(32),  primary_key=True),
    Column("customer_id",       String(32),  nullable=False, index=True),
    Column("subject",           String(200), nullable=False),
    Column("description",       Text,        nullable=False),
    Column("priority",          String(16),  nullable=False, default="medium"),
    Column("status",            String(20),  nullable=False, default="open"),
    Column("created_at",        String(32)),
    Column("updated_at",        String(32)),
    Column("escalated",         Boolean,     default=False),
    Column("escalation_reason", Text),
)

ticket_notes_t = Table(
    "ticket_notes", metadata,
    Column("id",        Integer,    primary_key=True, autoincrement=True),
    Column("ticket_id", String(32), nullable=False, index=True),
    Column("note",      Text,       nullable=False),
    Column("timestamp", String(32)),
)

refunds_t = Table(
    "refunds", metadata,
    Column("refund_id",  String(32), primary_key=True),
    Column("order_id",   String(32), nullable=False, index=True),
    Column("reason",     Text,       nullable=False),
    Column("status",     String(20), nullable=False, default="pending"),
    Column("created_at", String(32)),
)

conversations_t = Table(
    "conversations", metadata,
    Column("id",          Integer,    primary_key=True, autoincrement=True),
    Column("customer_id", String(32), nullable=False, index=True),
    Column("session_id",  String(64), nullable=True,  index=True),
    Column("role",        String(16), nullable=False),   # "user" | "assistant"
    Column("content",     Text,       nullable=False),
    Column("created_at",  String(32), nullable=False),
)

# ── Public API ────────────────────────────────────────────────────────────────

def now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def new_ticket_id() -> str:
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


def new_refund_id(order_id: str) -> str:
    return f"REF-{order_id[-4:]}-{uuid.uuid4().hex[:4].upper()}"


def save_conversation_turn(
    customer_id: str,
    role: str,
    content: str,
    session_id: str | None = None,
) -> None:
    """Persist a single conversation turn (user or assistant message)."""
    with engine.begin() as conn:
        conn.execute(insert(conversations_t).values(
            customer_id=customer_id.strip().upper(),
            session_id=session_id,
            role=role,
            content=content,
            created_at=now_iso(),
        ))


def get_conversation_history(
    customer_id: str,
    limit: int = 10,
    session_id: str | None = None,
) -> list[dict]:
    """Return the last *limit* turns for a customer, oldest-first.

    Args:
        customer_id: Customer identifier (case-insensitive).
        limit: Maximum number of messages to return (default 10 = 5 exchanges).
        session_id: Optional session scope; if None all sessions are included.
    """
    from sqlalchemy import desc, and_

    cid = customer_id.strip().upper()
    with engine.connect() as conn:
        q = select(conversations_t).where(conversations_t.c.customer_id == cid)
        if session_id is not None:
            q = q.where(conversations_t.c.session_id == session_id)
        q = q.order_by(desc(conversations_t.c.id)).limit(limit)
        rows = conn.execute(q).fetchall()
    # Reverse to chronological order
    return [{"role": r.role, "content": r.content, "created_at": r.created_at}
            for r in reversed(rows)]


def get_analytics_data() -> dict:
    """Return aggregated data for the analytics dashboard."""
    import time
    from datetime import timedelta
    from sqlalchemy import func, desc

    result: dict = {}

    with engine.connect() as conn:
        # ── Tickets ───────────────────────────────────────────────────
        total_tickets = conn.execute(
            select(func.count()).select_from(tickets_t)
        ).scalar() or 0

        rows = conn.execute(
            select(tickets_t.c.priority, func.count().label("cnt"))
            .group_by(tickets_t.c.priority)
        ).fetchall()
        by_priority = {row[0]: row[1] for row in rows}

        rows = conn.execute(
            select(tickets_t.c.status, func.count().label("cnt"))
            .group_by(tickets_t.c.status)
        ).fetchall()
        by_status = {row[0]: row[1] for row in rows}

        rows = conn.execute(
            select(tickets_t.c.customer_id, func.count().label("cnt"))
            .group_by(tickets_t.c.customer_id)
            .order_by(func.count().desc())
            .limit(20)
        ).fetchall()
        by_customer = {row[0]: row[1] for row in rows}

        # 7-day trend
        today = datetime.now(timezone.utc)
        trend_7d = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            date_prefix = day.strftime("%Y-%m-%d")
            cnt = conn.execute(
                select(func.count()).select_from(tickets_t).where(
                    tickets_t.c.created_at.like(f"{date_prefix}%")
                )
            ).scalar() or 0
            trend_7d.append({"date": date_prefix, "count": cnt})

        # Recent 10 tickets
        rows = conn.execute(
            select(
                tickets_t.c.ticket_id,
                tickets_t.c.customer_id,
                tickets_t.c.subject,
                tickets_t.c.priority,
                tickets_t.c.status,
                tickets_t.c.created_at,
            )
            .order_by(desc(tickets_t.c.created_at))
            .limit(10)
        ).fetchall()
        recent_tickets = [
            {
                "ticket_id":   row[0],
                "customer_id": row[1],
                "subject":     row[2],
                "priority":    row[3],
                "status":      row[4],
                "created_at":  row[5],
            }
            for row in rows
        ]

        result["tickets"] = {
            "total":       total_tickets,
            "by_priority": by_priority,
            "by_status":   by_status,
            "by_customer": by_customer,
            "trend_7d":    trend_7d,
            "recent":      recent_tickets,
        }

        # ── Orders ────────────────────────────────────────────────────
        total_orders = conn.execute(
            select(func.count()).select_from(orders_t)
        ).scalar() or 0

        rows = conn.execute(
            select(orders_t.c.status, func.count().label("cnt"))
            .group_by(orders_t.c.status)
        ).fetchall()
        orders_by_status = {row[0]: row[1] for row in rows}

        total_revenue = conn.execute(
            select(func.sum(orders_t.c.total)).select_from(orders_t)
        ).scalar() or 0.0

        result["orders"] = {
            "total":         total_orders,
            "by_status":     orders_by_status,
            "total_revenue": round(float(total_revenue), 2),
        }

        # ── Refunds ───────────────────────────────────────────────────
        total_refunds = conn.execute(
            select(func.count()).select_from(refunds_t)
        ).scalar() or 0

        rows = conn.execute(
            select(refunds_t.c.status, func.count().label("cnt"))
            .group_by(refunds_t.c.status)
        ).fetchall()
        refunds_by_status = {row[0]: row[1] for row in rows}

        result["refunds"] = {
            "total":     total_refunds,
            "by_status": refunds_by_status,
        }

    result["generated_at"] = time.time()
    return result


def init_db() -> None:
    """Create all tables; seed orders from JSON if the database is empty."""
    metadata.create_all(engine)
    _seed_orders_if_empty()
    logger.info("Database ready at %s", _DB_PATH)


# ── Seed helper ───────────────────────────────────────────────────────────────

def _seed_orders_if_empty() -> None:
    with engine.connect() as conn:
        first = conn.execute(select(orders_t).limit(1)).fetchone()
        if first is not None:
            return  # already seeded

    if not _ORDERS_JSON.exists():
        logger.warning("Seed file not found: %s — skipping seed", _ORDERS_JSON)
        return

    with open(_ORDERS_JSON, encoding="utf-8") as fh:
        raw: dict[str, Any] = json.load(fh)

    with engine.begin() as conn:
        for order_id, o in raw.items():
            items = o.pop("items", [])
            conn.execute(insert(orders_t).values(
                order_id=o.get("order_id", order_id),
                customer_id=o.get("customer_id", ""),
                status=o.get("status", "unknown"),
                subtotal=float(o.get("subtotal", 0)),
                shipping_cost=float(o.get("shipping_cost", 0)),
                total=float(o.get("total", 0)),
                shipping_address=o.get("shipping_address"),
                shipping_method=o.get("shipping_method"),
                created_at=o.get("created_at"),
                shipped_at=o.get("shipped_at"),
                delivered_at=o.get("delivered_at"),
                estimated_delivery=o.get("estimated_delivery"),
                cancelled_at=o.get("cancelled_at"),
                cancellation_reason=o.get("cancellation_reason"),
                tracking_number=o.get("tracking_number"),
                carrier=o.get("carrier"),
            ))
            for item in items:
                conn.execute(insert(order_items_t).values(
                    order_id=order_id,
                    product_id=item.get("product_id"),
                    name=item.get("name", ""),
                    quantity=int(item.get("quantity", 1)),
                    price=float(item.get("price", 0)),
                ))

    logger.info("Seeded %d orders from %s", len(raw), _ORDERS_JSON)
