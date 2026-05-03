"""Pydantic v2 request/response schemas for the CustomerSupport MCP Server."""

from pydantic import BaseModel, Field, field_validator


class CustomerRequest(BaseModel):
    """Validated input for the AI-powered handle_customer_request tool."""

    customer_id: str = Field(
        ...,
        min_length=4,
        max_length=32,
        description="Unique customer identifier, e.g. CUST-001.",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The customer's natural-language support query.",
    )

    @field_validator("customer_id")
    @classmethod
    def normalise_customer_id(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class TicketCreate(BaseModel):
    """Validated input for creating a support ticket."""

    customer_id: str = Field(..., description="Customer ID, e.g. CUST-001.")
    subject: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5, max_length=2000)
    priority: str = Field(default="medium", description="low | medium | high | critical")

    @field_validator("customer_id")
    @classmethod
    def normalise_customer_id(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        v = v.lower().strip()
        return v if v in {"low", "medium", "high", "critical"} else "medium"


class AgentResponse(BaseModel):
    """Structured response returned by the AI agent."""

    customer_id: str
    response: str
    model_used: str | None = None
    provider: str | None = None
    fallback_used: bool = False


class RateLimitInfo(BaseModel):
    """Rate-limit metadata embedded in error responses."""

    key: str
    remaining: int
    window_seconds: int
    max_requests: int
