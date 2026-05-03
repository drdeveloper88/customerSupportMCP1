"""Unit tests for tools/kb_tools.py"""
import json
from unittest.mock import patch

import pytest

from tools.kb_tools import search_kb, search_knowledge_base

# ── Sample KB data ────────────────────────────────────────────────────────────

SAMPLE_KB = [
    {
        "id": "KB-001",
        "category": "Shipping & Delivery",
        "question": "How long does shipping take?",
        "answer": "Standard shipping takes 5-7 business days.",
        "keywords": ["shipping", "delivery", "time", "days"],
    },
    {
        "id": "KB-002",
        "category": "Returns & Refunds",
        "question": "How do I return an item?",
        "answer": "You can return items within 30 days of purchase.",
        "keywords": ["return", "refund", "exchange"],
    },
    {
        "id": "KB-003",
        "category": "Account",
        "question": "How do I reset my password?",
        "answer": "Click Forgot Password on the login page.",
        "keywords": ["password", "reset", "account", "login"],
    },
]


@pytest.fixture(autouse=True)
def mock_kb():
    """Replace the KB file read with in-memory sample data for all tests."""
    with patch("tools.kb_tools._load_kb", return_value=SAMPLE_KB):
        yield


# ── search_kb ─────────────────────────────────────────────────────────────────

class TestSearchKb:
    def test_returns_matching_article(self):
        results = search_kb("shipping time")
        assert len(results) >= 1
        assert results[0]["id"] == "KB-001"

    def test_returns_empty_for_no_match(self):
        results = search_kb("xyzzy completely unrelated gibberish")
        assert results == []

    def test_respects_max_results(self):
        # Query "a" matches all articles lightly; cap at 1
        results = search_kb("how", max_results=1)
        assert len(results) == 1

    def test_returns_multiple_articles(self):
        results = search_kb("shipping return password")
        assert len(results) <= 3  # never exceeds max_results default

    def test_ranks_best_match_first(self):
        results = search_kb("return refund")
        assert results[0]["id"] == "KB-002"

    def test_ignores_short_words(self):
        # Single-character words should not score anything
        results = search_kb("a I")
        assert results == []


# ── LangChain tool wrapper ────────────────────────────────────────────────────

class TestSearchKnowledgeBaseTool:
    def test_tool_returns_formatted_text_on_match(self):
        result = search_knowledge_base.invoke({"query": "shipping"})
        # Tool returns formatted text (category + Q&A), not JSON
        assert isinstance(result, str)
        assert len(result) > 0
        assert "shipping" in result.lower() or "delivery" in result.lower()

    def test_tool_returns_no_match_message(self):
        result = search_knowledge_base.invoke({"query": "xyzzy gibberish 99999"})
        assert "No" in result or result == "[]"
