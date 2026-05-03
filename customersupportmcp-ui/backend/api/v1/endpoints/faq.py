"""GET /api/v1/faq – knowledge-base search endpoint (direct file access, no MCP transport)."""

from fastapi import APIRouter, Query

from services import support_service

router = APIRouter(prefix="/faq", tags=["FAQ"])


@router.get("", summary="Search the knowledge base")
async def search_faq(
    q: str = Query(default="", max_length=200, description="Search query"),
):
    """Full-text keyword search over FAQ articles. Returns an empty list for blank queries."""
    return await support_service.search_faq(q)
