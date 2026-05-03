"""GET /api/v1/orders/* – order lookup endpoints (direct DB, no MCP transport)."""

from fastapi import APIRouter, HTTPException, Path

from services import support_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/{customer_id}", summary="List all orders for a customer")
async def list_orders(
    customer_id: str = Path(..., min_length=1, max_length=64, examples=["CUST-001"]),
):
    """Return all orders belonging to the given customer ID."""
    return await support_service.fetch_orders(customer_id)


@router.get("/detail/{order_id}", summary="Get a single order by ID")
async def get_order(
    order_id: str = Path(..., min_length=1, max_length=64, examples=["ORD-1001"]),
):
    """Return full details and tracking info for a specific order."""
    result = await support_service.fetch_order(order_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    return result
