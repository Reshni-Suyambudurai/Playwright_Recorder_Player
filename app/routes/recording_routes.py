"""Recording API routes for saving and managing action recordings"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from app.models.recording import SaveRecordingRequest, Recording
from app.services.recording_service import RecordingService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recording"])


@router.post("/save-recording")
async def save_recording(request: SaveRecordingRequest):
    """
    Save action recording to JSON file
    
    Args:
        request: SaveRecordingRequest with recording data and metadata
        
    Returns:
        dict with save status and file details
    """
    try:
        logger.info(f"Saving recording: {request.title}")
        logger.debug(f"Recording ID: {request.recording.meta.id}")
        
        result = await run_in_threadpool(
            RecordingService.save_recording,
            request.recording,
            request.title,
            request.description or "",
            request.intent or ""
        )
        
        if result.get("status") == "success":
            logger.info(f"[OK] Recording saved successfully: {result['filename']}")
            return result
        else:
            logger.error(f"[FAIL] Failed to save recording: {result.get('message')}")
            raise HTTPException(status_code=500, detail=result.get("message", "Failed to save recording"))
            
    except Exception as e:
        logger.error(f"Error saving recording: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recording")
async def create_recording(recording: Recording):
    """
    Create and save a new recording
    
    Args:
        recording: Recording object with actions
        
    Returns:
        dict with save status and file details
    """
    try:
        logger.info(f"Creating recording: {recording.meta.title}")
        
        result = await run_in_threadpool(
            RecordingService.save_recording,
            recording,
            recording.meta.title,
            recording.meta.description,
            recording.meta.intent
        )
        
        if result.get("status") == "success":
            logger.info(f"[OK] Recording created successfully: {result['filename']}")
            return result
        else:
            logger.error(f"[FAIL] Failed to create recording: {result.get('message')}")
            raise HTTPException(status_code=500, detail=result.get("message", "Failed to create recording"))
            
    except Exception as e:
        logger.error(f"Error creating recording: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recordings")
async def list_recordings(limit: int = 10):
    """
    List recent recordings
    
    Args:
        limit: Maximum number of recordings to return (default: 10)
        
    Returns:
        dict with recordings list
    """
    try:
        logger.info(f"Listing recent recordings (limit: {limit})")
        
        result = await run_in_threadpool(
            RecordingService.list_recordings,
            limit
        )
        
        logger.info(f"[OK] Found {result.get('count', 0)} recordings")
        return result
        
    except Exception as e:
        logger.error(f"Error listing recordings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recording/{recording_id}")
async def get_recording(recording_id: str):
    """
    Get a specific recording by ID
    
    Args:
        recording_id: Recording ID (UUID)
        
    Returns:
        Recording data
    """
    try:
        logger.info(f"Fetching recording: {recording_id}")
        
        result = await run_in_threadpool(
            RecordingService.get_recording,
            recording_id
        )
        
        if result.get("status") == "success":
            logger.info(f"[OK] Recording found: {recording_id}")
            return result
        else:
            logger.warning(f"[WARN] Recording not found: {recording_id}")
            raise HTTPException(status_code=404, detail=result.get("message", "Recording not found"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recording: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
