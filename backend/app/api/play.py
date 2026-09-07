"""
REST endpoint: POST /play/start
Accepts the full recording JSON from the frontend, creates a PlaySession,
and returns the play_session_id for the frontend to connect over WebSocket.

Creates and manages playback sessions using REST APIs before playback starts over WebSocket.

creates Playback Session
"""
import asyncio
import uuid
import logging
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.models.playback import PlaySession
from app.models.playback_contracts import (
    StartPlaybackRequest,
    StartPlaybackResponse,
    StopPlaybackResponse,
)

logger = logging.getLogger("playwright_recorder.api.play")

# In-memory store: play_id -> PlaySession
_play_sessions: dict[str, PlaySession] = {}
_play_sessions_lock = asyncio.Lock()

# Session retention policy
PLAY_SESSION_TTL_SECONDS = 60 * 60
TERMINAL_SESSION_TTL_SECONDS = 10 * 60
PLAY_SESSION_SWEEP_INTERVAL_SECONDS = 60


def get_play_session(play_id: str) -> PlaySession | None:
    session = _play_sessions.get(play_id)
    if session:
        session.touch()
    return session


def _is_terminal_session(session: PlaySession) -> bool:
    return session.status.value in {"done", "error", "stopped"}


async def cleanup_expired_play_sessions() -> int:
    """Prune stale playback sessions from in-memory store."""
    async with _play_sessions_lock:
        to_remove: list[str] = []
        now = time.time()

        for play_id, session in _play_sessions.items():
            created_age = now - session.created_at
            last_access_age = now - session.last_accessed_at
            finished_age = now - session.finished_at if session.finished_at is not None else None

            if _is_terminal_session(session):
                if finished_age is not None and finished_age >= TERMINAL_SESSION_TTL_SECONDS:
                    to_remove.append(play_id)
                    continue
                if session.task and session.task.done() and last_access_age >= TERMINAL_SESSION_TTL_SECONDS:
                    to_remove.append(play_id)
                    continue

            if session.status.value == "pending" and created_age >= PLAY_SESSION_TTL_SECONDS:
                to_remove.append(play_id)

        for play_id in to_remove:
            _play_sessions.pop(play_id, None)

        if to_remove:
            logger.info(f"[PLAY] cleaned {len(to_remove)} expired session(s)")

        return len(to_remove)


async def play_session_cleanup_worker(stop_event: asyncio.Event) -> None:
    """Background sweeper for expired playback sessions."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PLAY_SESSION_SWEEP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            await cleanup_expired_play_sessions()
            continue
        break


def _count_steps(recording_json: dict) -> int:
    """Count total steps from nested structure"""
    count = 0
    steps_data = recording_json.get("steps", {})
    
    if isinstance(steps_data, dict):
        # Tab-based structure: {"tab-1": [[...], [...]], "tab-2": [...]}
        for tab_steps in steps_data.values():
            if isinstance(tab_steps, list):
                for step_array in tab_steps:
                    if isinstance(step_array, list):
                        for step in step_array:
                            if isinstance(step, dict) and step.get("type"):
                                count += 1
                    elif isinstance(step_array, dict) and step_array.get("type"):
                        count += 1
    elif isinstance(steps_data, list):
        # Flat list structure
        for step in steps_data:
            if isinstance(step, dict) and step.get("type"):
                count += 1
    
    return count


def create_play_router() -> APIRouter:
    router = APIRouter()

    @router.post("/start")
    async def start_playback(body: StartPlaybackRequest):
        """
        Accepts full recording JSON (with user-edited values merged in).
        Creates a PlaySession and returns play_session_id.
        
        Returns minimal response - live streaming will provide step details via WebSocket.
        """
        # Support both MCP format (recording_json) and legacy format (steps)
        recording_json = body.recording_json or {"steps": body.steps}
        
        if not recording_json.get("steps"):
            return JSONResponse(
                status_code=400,
                content={"detail": "Recording JSON must contain 'steps'"}
            )

        play_id = str(uuid.uuid4())
        session = PlaySession(play_id=play_id, recording_json=recording_json)
        
        # ✨ Use source and flags from request (MCP vs FastAPI)
        session.source = body.source
        session.capture_frames = body.capture_frames
        session.headless = body.headless
        
        logger.info(f"[PLAY] source={session.source}, capture_frames={session.capture_frames}, headless={session.headless}")
        
        async with _play_sessions_lock:
            _play_sessions[play_id] = session

        logger.info(f"[PLAY] session created: {play_id}")
        
        # ✨ LIVE STREAMING ONLY: Return minimal response
        # Step details will stream via WebSocket events
        total_steps = _count_steps(recording_json)
        
        if body.source == "mcp":
            logger.info(f"[PLAY] MCP response: play_session_id={play_id}, total_steps={total_steps}")
            return {
                "play_session_id": play_id,
                "total_steps": total_steps
            }
        else:
            # Web/FastAPI clients get standard response
            return StartPlaybackResponse(play_session_id=play_id)

    @router.delete("/{play_id}", response_model=StopPlaybackResponse)
    async def stop_playback(play_id: str):
        """Cancel a running playback session."""
        async with _play_sessions_lock:
            session = _play_sessions.get(play_id)
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Play session not found"})
        if session.task and not session.task.done():
            session.task.cancel()
        session.mark_finished()
        async with _play_sessions_lock:
            _play_sessions.pop(play_id, None)
        return StopPlaybackResponse(success=True)

    return router
