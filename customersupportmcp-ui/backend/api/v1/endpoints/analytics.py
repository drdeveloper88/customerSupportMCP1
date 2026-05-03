"""GET /api/v1/analytics – aggregated dashboard statistics."""

from fastapi import APIRouter

from services import support_service

router = APIRouter(tags=["Analytics"])


@router.get("/analytics", summary="Dashboard analytics snapshot")
async def get_analytics() -> dict:
    """
    Return aggregated analytics for the dashboard.

    Fields
    ------
    tickets        – total, by_priority, by_status, by_customer, trend_7d, recent
    orders         – total, by_status, total_revenue
    refunds        – total, by_status
    server         – active_connections, total_messages, avg_response_ms, uptime_seconds
    generated_at   – Unix epoch of this snapshot
    """
    return await support_service.get_analytics()
