"""Unit tests for tools/order_tools.py"""
import json

import pytest
from sqlalchemy import insert

from data.database import orders_t, order_items_t, now_iso
from tools.order_tools import (
    get_order_by_id,
    get_orders_by_customer,
    check_order_status,
    list_customer_orders,
    process_refund,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _insert_order(engine, order_id, customer_id, status="delivered"):
    """Insert a minimal order record for testing."""
    with engine.begin() as conn:
        conn.execute(insert(orders_t).values(
            order_id=order_id,
            customer_id=customer_id,
            status=status,
            subtotal=19.99,
            shipping_cost=2.99,
            total=22.98,
            shipping_address="1 Test St",
            shipping_method="standard",
            created_at=now_iso(),
            shipped_at=now_iso() if status in ("shipped", "delivered") else None,
            delivered_at=now_iso() if status == "delivered" else None,
            estimated_delivery=now_iso(),
            cancelled_at=None,
            cancellation_reason=None,
            tracking_number="TRK000",
            carrier="UPS",
        ))
        conn.execute(insert(order_items_t).values(
            order_id=order_id,
            product_id="PROD-X",
            name="Widget",
            quantity=1,
            price=19.99,
        ))


# ── get_order_by_id ───────────────────────────────────────────────────────────

class TestGetOrderById:
    def test_returns_order_when_found(self, mem_engine):
        _insert_order(mem_engine, "ORD-1001", "CUST-001")
        result = get_order_by_id("ORD-1001")
        assert result is not None
        assert result["order_id"] == "ORD-1001"
        assert "items" in result

    def test_returns_none_when_not_found(self):
        assert get_order_by_id("ORD-9999") is None

    def test_case_insensitive_lookup(self, mem_engine):
        _insert_order(mem_engine, "ORD-2001", "CUST-002")
        result = get_order_by_id("ord-2001")
        assert result is not None


# ── get_orders_by_customer ────────────────────────────────────────────────────

class TestGetOrdersByCustomer:
    def test_returns_all_customer_orders(self, mem_engine):
        _insert_order(mem_engine, "ORD-3001", "CUST-100")
        _insert_order(mem_engine, "ORD-3002", "CUST-100")
        orders = get_orders_by_customer("CUST-100")
        assert len(orders) == 2

    def test_returns_empty_for_unknown_customer(self):
        assert get_orders_by_customer("CUST-999") == []


# ── check_order_status @tool ──────────────────────────────────────────────────

class TestCheckOrderStatusTool:
    def test_returns_order_json(self, mem_engine):
        _insert_order(mem_engine, "ORD-4001", "CUST-001")
        result = check_order_status.invoke({"order_id": "ORD-4001"})
        data = json.loads(result)
        assert data["order_id"] == "ORD-4001"

    def test_invalid_format_returns_error_message(self):
        result = check_order_status.invoke({"order_id": "INVALID"})
        assert "Invalid" in result

    def test_not_found_returns_message(self):
        result = check_order_status.invoke({"order_id": "ORD-0000"})
        assert "No order found" in result


# ── list_customer_orders @tool ────────────────────────────────────────────────

class TestListCustomerOrdersTool:
    def test_returns_orders_json(self, mem_engine):
        _insert_order(mem_engine, "ORD-5001", "CUST-200")
        result = list_customer_orders.invoke({"customer_id": "CUST-200"})
        data = json.loads(result)
        assert len(data) == 1

    def test_invalid_customer_id_returns_error(self):
        result = list_customer_orders.invoke({"customer_id": "BAD"})
        assert "Invalid" in result

    def test_no_orders_returns_message(self):
        result = list_customer_orders.invoke({"customer_id": "CUST-404"})
        assert "No orders" in result


# ── process_refund @tool ──────────────────────────────────────────────────────

class TestProcessRefundTool:
    def test_refund_for_delivered_order(self, mem_engine):
        _insert_order(mem_engine, "ORD-6001", "CUST-001", status="delivered")
        result = process_refund.invoke({"order_id": "ORD-6001", "reason": "Wrong item"})
        assert "Refund request submitted" in result
        assert "ORD-6001" in result

    def test_refund_for_processing_order_rejected(self, mem_engine):
        _insert_order(mem_engine, "ORD-6002", "CUST-001", status="processing")
        result = process_refund.invoke({"order_id": "ORD-6002", "reason": "Changed mind"})
        # Refund is rejected; response mentions the current order state
        assert "process" in result.lower()  # matches 'processing' or 'processed'

    def test_refund_for_nonexistent_order(self):
        result = process_refund.invoke({"order_id": "ORD-0000", "reason": "Test"})
        assert "not found" in result

    def test_invalid_order_id_format(self):
        result = process_refund.invoke({"order_id": "BADFORMAT", "reason": "Test"})
        assert "Invalid" in result
