"""API routes for URL navigation"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
import logging
import traceback
from app.models.schemas import URLRequest
from app.services.launchWeb import browser_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["navigation"])


@router.post("/open-url")
async def open_url(request: URLRequest):
    """
    Open a URL in the browser
    
    Request body:
        - url: str (website URL)
    
    Returns:
        - status: success/error
        - url: the opened URL
    """
    try:
        logger.info(f"Open URL endpoint called with URL: {request.url}")
        if not request.url:
            logger.error("URL is empty")
            raise ValueError("URL cannot be empty")
        
        result = await run_in_threadpool(browser_manager.open_url, request.url)
        logger.debug(f"Open URL result: {result}")
        if result.get("status") == "success":
            logger.info(f"URL opened successfully: {request.url}")
            return result
        else:
            error_msg = result.get("message", "Failed to open URL")
            logger.error(f"Failed to open URL {request.url}: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in open_url: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
