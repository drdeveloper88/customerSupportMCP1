"""
Order management tools – SQLite real-time backend via SQLAlchemy.

All reads and writes hit the SQLite database in data/support.db.
The DB is auto-seeded from mock_orders.json on first run.
"""

import json
import logging
import re

from langchain_core.tools import tool
from sqlalchemy import insert, select

from data.database import (
    engine,
    new_refund_id,
    now_iso,
    order_items_t,
    orders_t,
    refunds_t,
)

logger = logging.getLogger(__name__)

_ORDER_ID_RE    = re.compile(r"^ORD-\d+$",  re.IGNORECASE)
_CUSTOMER_ID_RE = re.compile(r"^CUST-\d+$", re.IGNORECASE)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_items(conn, order_id: str) -> list[dict]:
    rows = conn.execute(
        select(order_items_t).where(order_items_t.c.order_id == order_id)
    ).fetchall()
    return [dict(r._mapping) for r in rows]


def _row_to_dict(row, items: list[dict]) -> dict:
    d = dict(row._mapping)
    d["items"] = items
    d.pop("id", None)
    return d


def get_order_by_id(order_id: str) -> dict | None:
    """Fetch a single order (with line items) from the database."""
    oid = order_id.strip().upper()
    with engine.connect() as conn:
        row = conn.execute(
            select(orders_t).where(orders_t.c.order_id == oid)
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row, _fetch_items(conn, oid))


def get_orders_by_customer(customer_id: str) -> list[dict]:
    """Fetch all orders for a given customer from the database."""
    cid = customer_id.strip().upper()
    with engine.connect() as conn:
        rows = conn.execute(
            select(orders_t).where(orders_t.c.customer_id == cid)
        ).fetchall()
        return [_row_to_dict(row, _fetch_items(conn, row.order_id)) for row in rows]


# ── LangChain @tool definitions ───────────────────────────────────────────────

@tool
def check_order_status(order_id: str) -> str:
    """Check the current status, tracking info, and full details of an order.

    Args:
        order_id: The order ID to look up (e.g. ORD-1001).
    """
    oid = order_id.strip().upper()
    if not _ORDER_ID_RE.match(oid):
        return f"Invalid order ID format '{order_id}'. Expected format: ORD-XXXX."
    order = get_order_by_id(oid)
    if not order:
        return f"No order found with ID '{oid}'. Please verify the order ID."
    return json.dumps(order, indent=2, default=str)


@tool
def list_customer_orders(customer_id: str) -> str:
    """List all orders placed by a customer.

    Args:
        customer_id: The customer ID (e.g. CUST-001).
    """
    cid = customer_id.strip().upper()
    if not _CUSTOMER_ID_RE.match(cid):
        return f"Invalid customer ID format '{customer_id}'. Expected format: CUST-XXX."
    orders = get_orders_by_customer(cid)
    if not orders:
        return f"No orders found for customer ID '{cid}'."
    return json.dumps(orders, indent=2, default=str)


@tool
def process_refund(order_id: str, reason: str) -> str:
    """Submit a refund request for a delivered or shipped order.

    Refund requests are persisted to the database and assigned a unique
    refund ID.  Processing takes 3-5 business days.

    Args:
        order_id: The order ID to refund (e.g. ORD-1001).
        reason:   The reason for the refund request.
    """
    oid = order_id.strip().upper()
    if not _ORDER_ID_RE.match(oid):
        return f"Invalid order ID format '{order_id}'. Expected format: ORD-XXXX."
    order = get_order_by_id(oid)
    if not order:
        return f"Cannot process refund: order '{oid}' not found."
    status = order.get("status", "unknown")
    if status in ("delivered", "shipped"):
        refund_id = new_refund_id(oid)
        with engine.begin() as conn:
            conn.execute(insert(refunds_t).values(
                refund_id=refund_id,
                order_id=oid,
                reason=reason.strip(),
                status="pending",
                created_at=now_iso(),
            ))
        logger.info("Refund %s created for order %s", refund_id, oid)
        return (
            f"Refund request submitted successfully.\n"
            f"  Order ID : {oid}\n"
            f"  Refund ID: {refund_id}\n"
            f"  Reason   : {reason.strip()}\n"
            f"  Status   : Pending review\n"
            f"  Expected processing time: 3-5 business days.\n"
            f"A confirmation email has been sent to the customer."
        )
    elif status == "processing":
        return (
            f"Order {oid} is still being processed. "
            "A refund cannot be raised yet — you may request a cancellation instead."
        )
    elif status == "cancelled":
        return f"Order {oid} is already cancelled. No refund action needed."
    else:
        return f"Refund cannot be processed for order {oid} with status '{status}'."
