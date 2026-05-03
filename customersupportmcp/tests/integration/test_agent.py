"""
Integration tests for agent/graph.py

These tests verify the full agent orchestration logic WITHOUT making real LLM API
calls.  The Groq and Ollama agent builders are patched to return lightweight mock
compiled graphs so tests run instantly and deterministically.

Scenarios covered
-----------------
- Happy path: single Groq model succeeds
- Groq rate-limit → fallback to next Groq model
- All Groq models exhausted → fallback to Ollama
- All providers fail → graceful error message returned
- No providers configured → immediate error message
- Ollama-only mode
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agent.graph import run_support_agent, _is_retriable_error


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fake_agent(response_text: str):
    """Return a mock compiled graph whose ainvoke returns a final AI message."""
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content=response_text)]}
    )
    return mock_agent


def _make_rate_limit_agent():
    """Return a mock agent whose ainvoke raises a rate-limit-like error."""
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(
        side_effect=Exception("rate_limit error: 429 Too Many Requests")
    )
    return mock_agent


# ── run_support_agent tests ────────────────────────────────────────────────────

class TestRunSupportAgent:
    async def test_happy_path_groq(self):
        """Agent returns the response from the first Groq model."""
        fake_agent = _make_fake_agent("Your order is on its way!")

        with (
            patch("agent.graph.GROQ_API_KEY", "test-key"),
            patch("agent.graph.GROQ_FALLBACK_MODELS", ["llama-3.1-8b-instant"]),
            patch("agent.graph.OLLAMA_ENABLED", False),
            patch("agent.graph._build_agent_groq", return_value=fake_agent),
            patch("agent.graph.get_conversation_history", return_value=[]),
            patch("agent.graph.save_conversation_turn"),
        ):
            result = await run_support_agent("CUST-001", "Where is my order?")

        assert "Your order is on its way!" in result

    async def test_groq_rate_limit_falls_back_to_second_model(self):
        """When the first Groq model hits a rate limit, the second Groq model is used."""
        failing_agent = _make_rate_limit_agent()
        success_agent = _make_fake_agent("Handled by fallback model.")

        call_count = 0

        def _build_side_effect(model_name):
            nonlocal call_count
            call_count += 1
            return failing_agent if call_count == 1 else success_agent

        with (
            patch("agent.graph.GROQ_API_KEY", "test-key"),
            patch("agent.graph.GROQ_FALLBACK_MODELS", ["model-a", "model-b"]),
            patch("agent.graph.OLLAMA_ENABLED", False),
            patch("agent.graph._build_agent_groq", side_effect=_build_side_effect),
            patch("agent.graph.get_conversation_history", return_value=[]),
            patch("agent.graph.save_conversation_turn"),
        ):
            result = await run_support_agent("CUST-002", "Help!")

        assert "Handled by fallback model." in result

    async def test_all_groq_exhausted_falls_back_to_ollama(self):
        """When all Groq models fail, Ollama is the last resort."""
        failing_agent = _make_rate_limit_agent()
        ollama_agent = _make_fake_agent("Ollama handled your request.")

        with (
            patch("agent.graph.GROQ_API_KEY", "test-key"),
            patch("agent.graph.GROQ_FALLBACK_MODELS", ["model-a"]),
            patch("agent.graph.OLLAMA_ENABLED", True),
            patch("agent.graph.OLLAMA_MODEL", "llama3.2"),
            patch("agent.graph._build_agent_groq", return_value=failing_agent),
            patch("agent.graph._build_agent_ollama", return_value=ollama_agent),
            patch("agent.graph.get_conversation_history", return_value=[]),
            patch("agent.graph.save_conversation_turn"),
        ):
            result = await run_support_agent("CUST-003", "Help!")

        assert "Ollama handled your request." in result

    async def test_all_providers_fail_returns_error_message(self):
        """When every provider raises, a polite error string is returned."""
        failing_agent = _make_rate_limit_agent()

        with (
            patch("agent.graph.GROQ_API_KEY", "test-key"),
            patch("agent.graph.GROQ_FALLBACK_MODELS", ["model-a"]),
            patch("agent.graph.OLLAMA_ENABLED", True),
            patch("agent.graph.OLLAMA_MODEL", "llama3.2"),
            patch("agent.graph._build_agent_groq", return_value=failing_agent),
            patch("agent.graph._build_agent_ollama", return_value=failing_agent),
            patch("agent.graph.get_conversation_history", return_value=[]),
            patch("agent.graph.save_conversation_turn"),
        ):
            result = await run_support_agent("CUST-004", "Help!")

        # Should not raise; should return a human-readable error
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_no_providers_configured_returns_error_message(self):
        """When neither Groq nor Ollama is configured, return an immediate message."""
        with (
            patch("agent.graph.GROQ_API_KEY", ""),
            patch("agent.graph.GROQ_FALLBACK_MODELS", []),
            patch("agent.graph.OLLAMA_ENABLED", False),
            patch("agent.graph.get_conversation_history", return_value=[]),
        ):
            result = await run_support_agent("CUST-005", "Help!")

        assert "No LLM provider" in result or "not configured" in result.lower()

    async def test_ollama_only_mode(self):
        """When no Groq key is set but Ollama is enabled, Ollama handles the request."""
        ollama_agent = _make_fake_agent("Ollama-only response.")

        with (
            patch("agent.graph.GROQ_API_KEY", ""),
            patch("agent.graph.GROQ_FALLBACK_MODELS", []),
            patch("agent.graph.OLLAMA_ENABLED", True),
            patch("agent.graph.OLLAMA_MODEL", "llama3.2"),
            patch("agent.graph._build_agent_ollama", return_value=ollama_agent),
            patch("agent.graph.get_conversation_history", return_value=[]),
            patch("agent.graph.save_conversation_turn"),
        ):
            result = await run_support_agent("CUST-006", "Test question.")

        assert "Ollama-only response." in result


# ── _is_retriable_error ────────────────────────────────────────────────────────

class TestIsRetriableError:
    @pytest.mark.parametrize("msg", [
        "rate_limit exceeded",
        "Error 429: Too Many Requests",
        "quota exceeded",
        "model is overloaded",
        "503 Service Unavailable",
        "502 Bad Gateway",
        "ratelimit",
    ])
    def test_returns_true_for_retriable_messages(self, msg):
        assert _is_retriable_error(Exception(msg)) is True

    @pytest.mark.parametrize("msg", [
        "Invalid API key",
        "NullPointerException",
        "400 Bad Request",
        "Not found",
    ])
    def test_returns_false_for_non_retriable_messages(self, msg):
        assert _is_retriable_error(Exception(msg)) is False
