"""
Recording API endpoints.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService

logger = logging.getLogger("playwright_recorder.api.recording")


class StopRecordingRequest(BaseModel):
    """Request model for stopping recording."""
    session_id: str


class RecordingAPI:
    """Handles recording-related API endpoints."""

    def __init__(self, session_manager: SessionManager, browser_service: BrowserService):
        self.session_manager = session_manager
        self.browser_service = browser_service

    async def start_recording(self) -> dict:
        """Start a new recording session."""
        logger.info("POST /recording/start called")
        try:
            session = self.session_manager.create_session()
            logger.info(f"Session created: {session.session_id}")

            logger.info(f"Launching browser for session: {session.session_id}")
            browser, browser_context, page = await self.browser_service.launch_browser()
            logger.info(f"Browser launched for session: {session.session_id}")

            session.browser = browser
            session.browser_context = browser_context
            session.page = page

            logger.info(f"Recording started successfully: {session.session_id}")
            return {
                "success": True,
                "session_id": session.session_id,
                "status": "Recording started"
            }

        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": str(e), "status": "Failed to start recording"}
            )

    async def stop_recording(self, session_id: str) -> dict:
        """Stop a recording session."""
        logger.info(f"POST /recording/stop called for session: {session_id}")
        try:
            session = self.session_manager.get_session(session_id)

            if not session:
                logger.warning(f"Session not found: {session_id}")
                raise HTTPException(
                    status_code=404,
                    detail={"success": False, "error": f"Session {session_id} not found", "status": "Session not found"}
                )

            logger.info(f"Closing browser for session: {session_id}")
            await self.browser_service.close_browser(session.browser)
            self.session_manager.remove_session(session_id)
            logger.info(f"Session stopped: {session_id}")

            return {"success": True, "session_id": session_id, "status": "Recording stopped"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to stop recording {session_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": str(e), "status": "Failed to stop recording"}
            )


def create_recording_router(session_manager: SessionManager, browser_service: BrowserService) -> APIRouter:
    """
    Create recording API router.
    
    Args:
        session_manager: SessionManager instance
        browser_service: BrowserService instance
        
    Returns:
        APIRouter: FastAPI router with recording endpoints
    """
    router = APIRouter()
    api = RecordingAPI(session_manager, browser_service)
    
    @router.post('/start')
    async def start():
        """Start recording endpoint."""
        return await api.start_recording()
    
    @router.post('/stop')
    async def stop(request: StopRecordingRequest):
        """Stop recording endpoint."""
        return await api.stop_recording(request.session_id)
    
    return router
