"""POST /api/v1/tickets – support ticket endpoints (direct DB, no MCP transport)."""

from fastapi import APIRouter, HTTPException, Path

from models.schemas import CreateTicketRequest
from services import support_service

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("", summary="Open a support ticket", status_code=201)
async def create_ticket(body: CreateTicketRequest):
    """Create a new support ticket for the given customer."""
    return await support_service.open_ticket(
        customer_id=body.customer_id,
        subject=body.subject,
        description=body.description,
        priority=body.priority,
    )


@router.get("/{ticket_id}", summary="Get a ticket by ID")
async def get_ticket(
    ticket_id: str = Path(..., min_length=1, max_length=64, examples=["TKT-0001"]),
):
    """Retrieve an existing support ticket by its ID."""
    result = await support_service.fetch_ticket(ticket_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
    return result
