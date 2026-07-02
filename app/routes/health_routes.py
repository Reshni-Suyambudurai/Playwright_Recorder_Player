"""API routes for health and status checks"""
from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint for API availability
    
    Returns:
        - status: ok/error
        - service: service name
    """
    logger.debug("Health check called")
    return {
        "status": "ok",
        "service": "Playwright Recorder Player"
    }
