"""API routes for screenshot operations"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pathlib import Path
import base64
import logging
from app.services.launchWeb import browser_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["screenshots"])


@router.post("/screenshot")
async def take_screenshot():
    """
    Take a screenshot of the current page
    
    Returns:
        - status: success/error
        - filename: screenshot filename
        - screenshot_path: path to saved screenshot
    """
    try:
        logger.info("Screenshot endpoint called")
        result = await run_in_threadpool(browser_manager.take_screenshot)
        if result.get("status") == "success":
            logger.info(f"Screenshot saved: {result.get('filename')}")
            return result
        else:
            error_msg = result.get("message", "Failed to take screenshot")
            logger.error(f"Screenshot failed: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in take_screenshot: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshots")
async def list_screenshots():
    """
    List all screenshots in the screenshots folder
    
    Returns:
        - status: success/error
        - screenshots: list of screenshot filenames
        - count: number of screenshots
    """
    try:
        logger.info("List screenshots endpoint called")
        screenshots_dir = Path(__file__).parent.parent / "screenshots"
        screenshots = [f.name for f in screenshots_dir.glob("*.png")]
        logger.debug(f"Found {len(screenshots)} screenshots")
        return {
            "status": "success",
            "screenshots": screenshots,
            "count": len(screenshots)
        }
    except Exception as e:
        logger.error(f"Error listing screenshots: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshot-base64")
async def get_screenshot_base64():
    """
    Get the most recent screenshot as base64 for display in grid
    
    Returns:
        - status: success/error
        - filename: screenshot filename
        - base64: image data (data:image/png;base64,...)
    """
    try:
        logger.info("Get screenshot base64 endpoint called")
        screenshots_dir = Path(__file__).parent.parent / "screenshots"
        screenshots = sorted(screenshots_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not screenshots:
            logger.warning("No screenshots found")
            return {"status": "error", "message": "No screenshots found"}
        
        latest_screenshot = screenshots[0]
        logger.debug(f"Using latest screenshot: {latest_screenshot.name}")
        
        # Read and encode as base64
        with open(latest_screenshot, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        logger.info(f"Screenshot converted to base64: {latest_screenshot.name}")
        return {
            "status": "success",
            "filename": latest_screenshot.name,
            "base64": f"data:image/png;base64,{image_data}"
        }
    except Exception as e:
        logger.error(f"Error getting screenshot base64: {str(e)}")
        return {"status": "error", "message": str(e)}
