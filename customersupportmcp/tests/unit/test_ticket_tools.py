"""Unit tests for tools/ticket_tools.py"""
import pytest

from tools.ticket_tools import (
    create_support_ticket,
    get_ticket_by_id,
    update_ticket_status,
    do_escalate_ticket,
    create_ticket_tool,
    get_ticket_info,
    escalate_ticket_tool,
)


# ── create_support_ticket ─────────────────────────────────────────────────────

class TestCreateSupportTicket:
    def test_creates_ticket_with_all_fields(self):
        ticket = create_support_ticket("CUST-001", "Missing item", "I am missing item X.", "high")
        assert ticket["customer_id"] == "CUST-001"
        assert ticket["subject"] == "Missing item"
        assert ticket["priority"] == "high"
        assert ticket["status"] == "open"
        assert ticket["ticket_id"].startswith("TKT-")

    def test_invalid_priority_defaults_to_medium(self):
        ticket = create_support_ticket("CUST-002", "Sub", "Desc", "invalid_priority")
        assert ticket["priority"] == "medium"

    def test_customer_id_is_uppercased(self):
        ticket = create_support_ticket("cust-003", "Sub", "Desc")
        assert ticket["customer_id"] == "CUST-003"

    def test_notes_empty_on_creation(self):
        ticket = create_support_ticket("CUST-004", "Sub", "Desc")
        assert ticket["notes"] == []


# ── get_ticket_by_id ──────────────────────────────────────────────────────────

class TestGetTicketById:
    def test_returns_ticket_when_found(self, sample_ticket):
        result = get_ticket_by_id(sample_ticket["ticket_id"])
        assert result is not None
        assert result["ticket_id"] == sample_ticket["ticket_id"]

    def test_returns_none_for_unknown_id(self):
        assert get_ticket_by_id("TKT-00000000") is None

    def test_case_insensitive(self, sample_ticket):
        lower = sample_ticket["ticket_id"].lower()
        result = get_ticket_by_id(lower)
        assert result is not None


# ── update_ticket_status ──────────────────────────────────────────────────────

class TestUpdateTicketStatus:
    def test_updates_status(self, sample_ticket):
        updated = update_ticket_status(sample_ticket["ticket_id"], "pending")
        assert updated["status"] == "pending"

    def test_appends_note(self, sample_ticket):
        update_ticket_status(sample_ticket["ticket_id"], "resolved", note="Customer confirmed fix.")
        ticket = get_ticket_by_id(sample_ticket["ticket_id"])
        assert any("Customer confirmed fix." in n["note"] for n in ticket["notes"])

    def test_invalid_status_defaults_to_open(self, sample_ticket):
        updated = update_ticket_status(sample_ticket["ticket_id"], "completely_wrong")
        assert updated["status"] == "open"

    def test_returns_none_for_nonexistent_ticket(self):
        assert update_ticket_status("TKT-00000000", "resolved") is None


# ── do_escalate_ticket ────────────────────────────────────────────────────────

class TestDoEscalateTicket:
    def test_escalates_ticket(self, sample_ticket):
        updated = do_escalate_ticket(sample_ticket["ticket_id"], "Customer is very upset.")
        assert updated["status"] == "escalated"
        assert updated["escalated"] is True
        assert updated["priority"] == "high"

    def test_adds_escalation_note(self, sample_ticket):
        do_escalate_ticket(sample_ticket["ticket_id"], "Urgent complaint.")
        ticket = get_ticket_by_id(sample_ticket["ticket_id"])
        assert any("Escalated" in n["note"] for n in ticket["notes"])

    def test_returns_none_for_missing_ticket(self):
        assert do_escalate_ticket("TKT-00000000", "reason") is None


# ── LangChain tool wrappers ───────────────────────────────────────────────────

class TestCreateTicketTool:
    def test_returns_confirmation_message(self):
        result = create_ticket_tool.invoke({
            "customer_id": "CUST-010",
            "subject": "Order not arrived",
            "description": "My order has not arrived after 14 days.",
            "priority": "high",
        })
        assert "Support ticket created" in result
        assert "TKT-" in result


class TestGetTicketInfoTool:
    def test_returns_ticket_details(self, sample_ticket):
        result = get_ticket_info.invoke({"ticket_id": sample_ticket["ticket_id"]})
        assert sample_ticket["ticket_id"] in result

    def test_returns_not_found_message(self):
        result = get_ticket_info.invoke({"ticket_id": "TKT-00000000"})
        assert "not found" in result.lower() or "No ticket" in result


class TestEscalateTicketTool:
    def test_escalates_and_returns_confirmation(self, sample_ticket):
        result = escalate_ticket_tool.invoke({
            "ticket_id": sample_ticket["ticket_id"],
            "reason": "Customer threatening legal action.",
        })
        assert "escalated" in result.lower()

    def test_not_found_returns_message(self):
        result = escalate_ticket_tool.invoke({
            "ticket_id": "TKT-00000000",
            "reason": "test",
        })
        assert "not found" in result.lower() or "No ticket" in result
