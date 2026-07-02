"""Playback API routes for replaying recorded actions"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from app.services.playback_service import PlaybackService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["playback"])


@router.post("/playback/{recording_id}")
async def playback_recording(recording_id: str):
    """
    Playback a recording by ID
    
    Args:
        recording_id: Recording ID (UUID)
        
    Returns:
        dict with playback results and action logs
    """
    try:
        logger.info(f"Starting playback request for recording: {recording_id}")
        
        result = await run_in_threadpool(
            PlaybackService.play_recording,
            recording_id
        )
        
        if result.get("status") in ["success", "partial"]:
            logger.info(f"[OK] Playback completed: {result['overall_status']}")
            logger.info(f"  Actions completed: {result['completed_actions']}/{result['total_actions']}")
            return result
        else:
            logger.error(f"[FAIL] Playback failed: {result.get('message')}")
            raise HTTPException(status_code=404, detail=result.get("message", "Playback failed"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during playback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/playback-simulate/{recording_id}")
async def playback_recording_simulate(recording_id: str):
    """
    Simulate playback without executing (for testing/review)
    
    Args:
        recording_id: Recording ID (UUID)
        
    Returns:
        dict with simulated action sequence
    """
    try:
        logger.info(f"Simulating playback for recording: {recording_id}")
        
        recording_data = await run_in_threadpool(
            PlaybackService.load_recording,
            recording_id
        )
        
        if not recording_data:
            raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
        
        steps = recording_data.get("steps", {}).get("tab-1", [])
        all_actions = []
        for action_group in steps:
            all_actions.extend(action_group)
        
        return {
            "status": "success",
            "recording_id": recording_id,
            "title": recording_data.get("meta", {}).get("title", "Untitled"),
            "total_actions": len(all_actions),
            "actions_preview": [
                {
                    "id": idx + 1,
                    "type": action.get("type"),
                    "description": PlaybackService._get_action_description(action),
                    "timestamp": action.get("timestamp")
                }
                for idx, action in enumerate(all_actions)
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error simulating playback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@staticmethod
def _get_action_description(action: dict) -> str:
    """Get human-readable description of action"""
    action_type = action.get("type", "UNKNOWN")
    
    if action_type == "NAVIGATE":
        return f"Navigate to {action.get('url', 'unknown')}"
    elif action_type == "CLICK":
        label = action.get("label", "")
        tag = action.get("tag", "element")
        return f"Click {tag}: {label}" if label else f"Click {tag}"
    elif action_type == "TYPE":
        label = action.get("label", "")
        text_preview = action.get("text", "")[:20]
        return f"Type in {label}: {text_preview}..." if label else f"Type: {text_preview}..."
    elif action_type == "SCROLL":
        return f"Scroll {action.get('deltaY', 0)}px"
    elif action_type == "WAIT":
        return f"Wait {action.get('waitAfterMs', 1000)}ms"
    else:
        return action_type


# Add method to PlaybackService
PlaybackService._get_action_description = staticmethod(_get_action_description)
