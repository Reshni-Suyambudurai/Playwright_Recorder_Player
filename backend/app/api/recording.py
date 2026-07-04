"""
Recording API endpoints.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService
from app.services.database import DatabaseService
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger("playwright_recorder.api.recording")


class StopRecordingRequest(BaseModel):
    """Request model for stopping recording."""
    session_id: str


class RecordingAPI:
    """Handles recording-related API endpoints."""

    def __init__(self, session_manager: SessionManager, browser_service: BrowserService, connection_manager: ConnectionManager | None = None):
        self.session_manager = session_manager
        self.browser_service = browser_service
        self.connection_manager = connection_manager

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

            # Detach DomWatcher BEFORE closing the browser to prevent TargetClosedError
            if session.dom_watcher:
                await session.dom_watcher.detach()
                session.dom_watcher = None

            # Notify the connected client so the frontend can update its state
            if self.connection_manager:
                client_id = getattr(session, 'client_id', None) or ""
                try:
                    await self.connection_manager.send_to_client(
                        session_id, client_id,
                        {"event_type": "SESSION_CLOSED", "data": {"reason": "Session ended"}},
                    )
                except Exception:
                    pass  # client may already be gone

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


def create_recording_router(session_manager: SessionManager, browser_service: BrowserService, db: DatabaseService | None = None, connection_manager: ConnectionManager | None = None) -> APIRouter:
    """
    Create recording API router.
    """
    router = APIRouter()
    api = RecordingAPI(session_manager, browser_service, connection_manager)

    @router.post('/start')
    async def start():
        """Start recording endpoint."""
        return await api.start_recording()

    @router.post('/stop')
    async def stop(request: StopRecordingRequest):
        """Stop recording endpoint."""
        return await api.stop_recording(request.session_id)

    @router.get('/list')
    async def list_recordings():
        """List all recordings from the database."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not available")
        return await db.list_recordings()

    @router.get('/{record_id}')
    async def get_recording(record_id: str):
        """Return the full JSON for a single recording."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not available")
        data = await db.load_recording(record_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Recording '{record_id}' not found")
        return data

    return router
