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
from app.services.database import DatabaseService

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


async def shutdown_play_sessions() -> int:
    """Cancel and await all playback tasks, then close any remaining resources."""
    async with _play_sessions_lock:
        sessions = list(_play_sessions.values())
        _play_sessions.clear()

    tasks = [session.task for session in sessions if session.task is not None]
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    for session in sessions:
        if session.dom_watcher:
            try:
                await session.dom_watcher.detach()
            except Exception as exc:
                logger.warning(f"[PLAY:{session.play_id}] watcher shutdown failed: {exc}")
            session.dom_watcher = None
        if session.browser_context:
            try:
                await session.browser_context.close()
            except Exception as exc:
                logger.warning(f"[PLAY:{session.play_id}] context shutdown failed: {exc}")
            session.browser_context = None
        if session.browser:
            try:
                await session.browser.close()
            except Exception as exc:
                logger.warning(f"[PLAY:{session.play_id}] browser shutdown failed: {exc}")
            session.browser = None
        session.page = None
        session.mark_finished()

    if sessions:
        logger.info(f"[PLAY] shut down {len(sessions)} session(s)")
    return len(sessions)


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


def create_play_router(db: DatabaseService | None = None) -> APIRouter:
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
        session.enable_pause_recording = body.enable_pause_recording
        session.original_recording_id = body.original_recording_id
        
        logger.info(f"[PLAY] source={session.source}, capture_frames={session.capture_frames}, headless={session.headless}, pause_recording={body.enable_pause_recording}")
        
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

    @router.post("/{play_id}/save_paused_recording")
    async def save_paused_recording(play_id: str, body: dict):
        """
        Save recording with captured pause steps.
        Options:
        - cancel: discard pause steps
        - save_as_new: create new recording, keep original
        - save_delete_old: replace original recording
        """
        from app.services.recording_storage import RecordingStorage
        from app.utils.recording_merge import merge_pause_steps_with_reinsertion
        from app.models.recording import Recording, RecordingMeta
        
        async with _play_sessions_lock:
            session = _play_sessions.get(play_id)
        
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Play session not found"})
        
        save_option = body.get("save_option", "cancel")  # cancel | save_as_new | save_delete_old
        title = body.get("title", "")
        intent = body.get("intent", "")
        description = body.get("description", "")
        
        # If no pause steps captured or user cancels
        if not session.pause_step_insertion_points or save_option == "cancel":
            logger.info(f"[PLAY:{play_id}] Pause recording cancelled")
            async with _play_sessions_lock:
                _play_sessions.pop(play_id, None)
            return {"success": True, "message": "Pause steps discarded"}
        
        try:
            # Load original recording
            storage = RecordingStorage()
            if not session.original_recording_id:
                return JSONResponse(status_code=400, content={"error": "No original recording ID found"})

            if not db:
                return JSONResponse(status_code=503, content={"error": "Database not available"})

            original_data = await db.load_recording(session.original_recording_id)
            if not original_data:
                return JSONResponse(status_code=404, content={"error": "Original recording not found"})

            original_recording = Recording.model_validate(original_data)
            original_step_count = _count_steps(original_data)

            # Merge pause steps with original recording
            merged_steps, total_steps = merge_pause_steps_with_reinsertion(
                original_recording,
                session.pause_step_insertion_points
            )
            
            # Create new recording metadata
            new_recording_id = str(uuid.uuid4())
            new_meta = RecordingMeta(
                id=new_recording_id,
                title=title or f"{original_recording.meta.title} - Extended",
                description=description or f"Extended with {total_steps - original_step_count} pause steps",
                intent=intent or original_recording.meta.intent,
                created_at=int(time.time() * 1000),
                updated_at=int(time.time() * 1000),
                viewport=original_recording.meta.viewport,
            )
            
            # Create new recording with merged steps
            new_recording = Recording(
                version="1.0",
                meta=new_meta,
                steps=merged_steps,
            )

            recording_json = new_recording.model_dump(by_alias=True)
            client_id = original_recording.meta.id
            await db.ensure_user(client_id)
            await db.save_recording(
                record_id=new_recording_id,
                client_id=client_id,
                recording_json=recording_json,
                flow_name=new_meta.title,
            )
            storage.save(new_recording)
            
            # Delete old recording if requested
            if save_option == "save_delete_old":
                try:
                    await db.delete_recording(session.original_recording_id)
                    storage.delete(session.original_recording_id)
                    logger.info(f"[PLAY:{play_id}] Deleted original recording {session.original_recording_id}")
                except Exception as e:
                    logger.warning(f"[PLAY:{play_id}] Failed to delete original recording: {e}")
            
            logger.info(f"[PLAY:{play_id}] Saved paused recording: {new_recording_id} (option: {save_option})")
            
            async with _play_sessions_lock:
                _play_sessions.pop(play_id, None)
            
            return {
                "success": True,
                "recording_id": new_recording_id,
                "total_steps": total_steps,
                "message": f"Recording saved as {'new' if save_option == 'save_as_new' else 'replacement'}"
            }
            
        except Exception as e:
            logger.error(f"[PLAY:{play_id}] Error saving paused recording: {e}", exc_info=True)
            return JSONResponse(status_code=500, content={"error": str(e)})

    return router
