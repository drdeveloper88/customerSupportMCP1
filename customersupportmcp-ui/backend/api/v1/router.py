"""
API v1 router — aggregates all endpoint routers under /api/v1.
"""

from fastapi import APIRouter

from api.v1.endpoints import analytics, auth, chat, faq, health, metrics, orders, tickets

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(health.router)
router.include_router(chat.router)
router.include_router(orders.router)
router.include_router(faq.router)
router.include_router(tickets.router)
router.include_router(metrics.router)
router.include_router(analytics.router)
