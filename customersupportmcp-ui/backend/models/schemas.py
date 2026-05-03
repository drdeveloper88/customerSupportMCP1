"""
Pydantic request/response models for the Customer Support MCP API.

All user-supplied inputs are validated and sanitised here so that
endpoint handlers receive guaranteed-clean data.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Compile-time regex constants ──────────────────────────────────────────────

_CUSTOMER_ID_RE = re.compile(r"^CUST-\d{3,}$")
_ORDER_ID_RE    = re.compile(r"^ORD-\d+$")
_TICKET_ID_RE   = re.compile(r"^TKT-[0-9A-F]{8}$", re.IGNORECASE)
_SAFE_TEXT_RE   = re.compile(r"[<>{}\[\]\\]")          # reject common injection chars

_VALID_PRIORITIES = frozenset({"low", "medium", "high", "critical"})


# ── Request models ────────────────────────────────────────────────────────────


class CreateTicketRequest(BaseModel):
    """Payload for POST /api/v1/tickets."""

    customer_id: str = Field(..., min_length=1, max_length=64, examples=["CUST-001"])
    subject:     str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5, max_length=2000)
    priority:    str = Field("medium")

    # ── Field-level validators ────────────────────────────────────────────────

    @field_validator("customer_id", mode="before")
    @classmethod
    def normalise_customer_id(cls, v: str) -> str:
        v = v.strip().upper()
        if not _CUSTOMER_ID_RE.match(v):
            raise ValueError(
                f"customer_id must match CUST-NNN format (got '{v}')"
            )
        return v

    @field_validator("subject", "description", mode="before")
    @classmethod
    def strip_and_reject_injection(cls, v: str) -> str:
        v = v.strip()
        if _SAFE_TEXT_RE.search(v):
            raise ValueError("Field contains disallowed characters (< > { } [ ] \\)")
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def normalise_priority(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _VALID_PRIORITIES:
            raise ValueError(
                f"priority must be one of {sorted(_VALID_PRIORITIES)} (got '{v}')"
            )
        return v

    # ── Cross-field validator ─────────────────────────────────────────────────

    @model_validator(mode="after")
    def subject_not_in_description(self) -> "CreateTicketRequest":
        if self.subject and self.description:
            if self.subject.lower() == self.description.lower():
                raise ValueError("subject and description must not be identical")
        return self


class ChatMessage(BaseModel):
    """Payload received over the WebSocket."""

    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


# ── Response models ───────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status:  str = "ok"
    version: str
    service: str


class ToolListResponse(BaseModel):
    tools: list[dict[str, Any]]


class ErrorResponse(BaseModel):
    error:      str
    detail:     str | None = None
    request_id: str | None = None
