"""
Recording API endpoints.

Spring Boot                     FastAPI Project
--------------------------------------------------------
@Entity / DTO            -->    Recording Model
Repository               -->    RecordingStorage
Service                  -->    WebSocketHandler
Controller               -->    recording.py

"""
import logging
import time
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
        t0 = time.perf_counter()
        logger.info("[RECORDING START] POST /recording/start called")
        try:
            session = self.session_manager.create_session()
            logger.info("[RECORDING START] session created: %s", session.session_id)

            logger.info("[RECORDING START] launching browser for session: %s", session.session_id)
            t_launch = time.perf_counter()
            browser, browser_context, page = await self.browser_service.launch_browser()
            logger.info(
                "[RECORDING START] browser launch completed for session: %s in %dms",
                session.session_id,
                int((time.perf_counter() - t_launch) * 1000),
            )

            session.browser = browser
            session.browser_context = browser_context
            session.page = page

            logger.info(
                "[RECORDING START] success session=%s total=%dms",
                session.session_id,
                int((time.perf_counter() - t0) * 1000),
            )
            return {
                "success": True,
                "session_id": session.session_id,
                "status": "Recording started"
            }

        except Exception as e:
            logger.error(
                "[RECORDING START] failed after %dms: %s",
                int((time.perf_counter() - t0) * 1000),
                e,
                exc_info=True,
            )
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

    @router.delete('/{record_id}')
    async def delete_recording(record_id: str):
        """Delete a recording by ID."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not available")
        deleted = await db.delete_recording(record_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Recording '{record_id}' not found")
        return {"success": True, "recordId": record_id}

    @router.put('/{record_id}')
    async def update_recording(record_id: str, body: dict):
        """
        Replace the JSON of an existing recording (e.g. edited step text values).
        The body must be the full recording JSON ({ version, meta, steps }).
        """
        if not db:
            raise HTTPException(status_code=503, detail="Database not available")
        existing = await db.load_recording(record_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Recording '{record_id}' not found")
        meta = body.get("meta", {})
        flow_name = meta.get("title", "Untitled")
        # Reuse the same userId from the existing record
        client_id = existing.get("meta", {}).get("id", record_id)
        # Ensure the Users row exists before writing (avoids FK constraint failure)
        await db.ensure_user(client_id)
        await db.save_recording(
            record_id=record_id,
            client_id=client_id,
            recording_json=body,
            flow_name=flow_name,
        )
        return {"success": True, "recordId": record_id}

    return router
