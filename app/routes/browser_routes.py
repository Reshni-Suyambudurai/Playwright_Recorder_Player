"""API routes for browser operations"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
import logging
import traceback
from app.services.launchWeb import browser_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["browser"])


@router.post("/initialize")
async def initialize_browser():
    """
    Initialize the browser with predefined viewport (1280x720)
    
    Returns:
        - status: success/error
        - message: initialization message
        - viewport: viewport configuration
    """
    try:
        logger.info("Initialize endpoint called")
        result = await run_in_threadpool(browser_manager.initialize)
        logger.debug(f"Initialize result: {result}")
        if result.get("status") == "success":
            logger.info("Browser initialization successful")
            return {
                "status": "success",
                "message": result.get("message", "Browser initialized"),
                "viewport": browser_manager.viewport
            }
        else:
            error_msg = result.get("message", "Failed to initialize")
            logger.error(f"Browser initialization failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in initialize: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_browser():
    """
    Close the browser and cleanup resources
    
    Returns:
        - status: success/error
        - message: closure message
    """
    try:
        logger.info("Close endpoint called")
        result = await run_in_threadpool(browser_manager.close)
        if result.get("status") == "success":
            logger.info("Browser closed successfully")
            return result
        else:
            error_msg = result.get("message", "Failed to close")
            logger.error(f"Browser close failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in close: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
