"""
REST endpoint: POST /play/start
Accepts the full recording JSON from the frontend, creates a PlaySession,
and returns the play_session_id for the frontend to connect over WebSocket.
"""
import uuid
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.models.playback import PlaySession

logger = logging.getLogger("playwright_recorder.api.play")

# In-memory store: play_id -> PlaySession
_play_sessions: dict[str, PlaySession] = {}


def get_play_session(play_id: str) -> PlaySession | None:
    return _play_sessions.get(play_id)


def create_play_router() -> APIRouter:
    router = APIRouter()

    @router.post("/start")
    async def start_playback(body: dict):
        """
        Accepts full recording JSON (with user-edited values merged in).
        Creates a PlaySession and returns play_session_id.
        The client then opens WS /ws/play/{play_session_id} to stream frames.
        """
        if not body.get("steps"):
            return JSONResponse(
                status_code=400,
                content={"detail": "Recording JSON must contain 'steps'"}
            )

        play_id = str(uuid.uuid4())
        session = PlaySession(play_id=play_id, recording_json=body)
        _play_sessions[play_id] = session

        logger.info(f"[PLAY] session created: {play_id}")
        return {"play_session_id": play_id}

    @router.delete("/{play_id}")
    async def stop_playback(play_id: str):
        """Cancel a running playback session."""
        session = get_play_session(play_id)
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Play session not found"})
        if session.task and not session.task.done():
            session.task.cancel()
        _play_sessions.pop(play_id, None)
        return {"success": True}

    return router
