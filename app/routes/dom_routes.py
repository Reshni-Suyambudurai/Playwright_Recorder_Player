"""API routes for DOM and element operations"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
import logging
import traceback
from app.models.schemas import CoordinatesRequest
from app.services.launchWeb import browser_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dom"])


@router.get("/dom")
async def get_dom():
    """
    Fetch the DOM of the current page
    
    Returns:
        - status: success/error
        - html: page HTML content
        - viewport: viewport dimensions
    """
    try:
        logger.info("Get DOM endpoint called")
        result = await run_in_threadpool(browser_manager.get_dom)
        if result.get("status") == "success":
            logger.info("DOM fetched successfully")
            return result
        else:
            error_msg = result.get("message", "Failed to get DOM")
            logger.error(f"Get DOM failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_dom: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/element-at-coordinates")
async def get_element_at_coordinates(request: CoordinatesRequest):
    """
    Get element information at specific coordinates (x, y)
    
    Request body:
        - x: int (pixel X coordinate, 0-1280)
        - y: int (pixel Y coordinate, 0-720)
    
    Returns:
        - status: success/error
        - coordinates: requested coordinates
        - element: element information (tag, id, class, selector, xpath, attributes, etc.)
    """
    try:
        logger.info(f"Get element at coordinates endpoint called: X={request.x}, Y={request.y}")
        
        if not (0 <= request.x <= 1280) or not (0 <= request.y <= 720):
            logger.error(f"Coordinates out of bounds: X={request.x}, Y={request.y}")
            raise ValueError(f"Coordinates must be within viewport (0-1280, 0-720)")
        
        result = await run_in_threadpool(browser_manager.get_element_at_coordinates, request.x, request.y)
        if result.get("status") == "success":
            logger.info(f"Element found at {request.x}, {request.y}")
            return result
        else:
            error_msg = result.get("message", "Element not found")
            logger.warning(f"No element at {request.x}, {request.y}: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_element_at_coordinates: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
