"""
Main entry point for the Playwright Recorder backend application.
"""
import logging
import os
import sys
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService
from app.services.screenshot_service import ScreenshotService
from app.services.database import DatabaseService
from app.api.recording import create_recording_router
from app.api.play import create_play_router, get_play_session
from app.websocket.connection_manager import ConnectionManager
from app.websocket.websocket_handler import WebSocketHandler
from app.services.playback_service import PlaybackService
from app.websocket.playback_handler import PlaybackHandler
from app.utils import tab_manager

# ==================== Logging Setup ====================
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("playwright_recorder")


def create_app():
    """Create and configure the FastAPI application."""
    logger.info("Creating FastAPI application")

    db = DatabaseService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("App startup: initialising database")
        await db.init_db()
        yield
        logger.info("App shutdown")

    app = FastAPI(title="Playwright Recorder API", version="1.0.0", lifespan=lifespan)

    # Enable CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize services
    session_manager = SessionManager()
    browser_service = BrowserService()
    connection_manager = ConnectionManager()
    screenshot_service = ScreenshotService(browser_service, connection_manager)
    websocket_handler = WebSocketHandler(connection_manager, session_manager, browser_service, screenshot_service, db)
    playback_service  = PlaybackService(browser_service, screenshot_service, connection_manager)
    playback_handler  = PlaybackHandler(connection_manager, playback_service, browser_service)
    logger.info("All services initialized")

    # Register routers
    recording_router = create_recording_router(session_manager, browser_service, db, connection_manager)
    app.include_router(recording_router, prefix="/recording")
    logger.info("Recording router registered at /recording")

    play_router = create_play_router()
    app.include_router(play_router, prefix="/play")
    logger.info("Play router registered at /play")

    # WebSocket endpoint
    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        logger.info(f"WebSocket connection attempt for session: {session_id}")

        session = session_manager.get_session(session_id)
        if not session:
            logger.warning(f"WebSocket rejected: session {session_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
            return

        await websocket.accept()
        await connection_manager.connect(session_id, websocket)
        logger.info(f"WebSocket accepted for session: {session_id}")

        try:
            while True:
                data = await websocket.receive_text()
                logger.debug(f"[WS] Received from {session_id}: {data}")

                try:
                    event_data = json.loads(data)
                    # handle_event now owns sending the response to the right client
                    await websocket_handler.handle_event(session_id, websocket, event_data)

                except json.JSONDecodeError as e:
                    logger.error(f"[WS] JSON decode error for session {session_id}: {e}")
                    error_response = websocket_handler._error_response(
                        "JSON_DECODE_ERROR",
                        f"Invalid JSON: {str(e)}"
                    )
                    await websocket.send_json(error_response)

        except WebSocketDisconnect:
            logger.info(f"[WS] Client disconnected from session {session_id}")
            # Detach all tab watchers so no more frames are emitted for this client
            session = session_manager.get_session(session_id)
            if session:
                await tab_manager.detach_all_watchers(session)
                if session.dom_watcher:
                    await session.dom_watcher.detach()
                    session.dom_watcher = None
            await connection_manager.disconnect(websocket)

        except Exception as e:
            logger.error(f"[WS] Unexpected error in session {session_id}: {e}", exc_info=True)
            await connection_manager.disconnect(websocket)

    @app.get("/health")
    async def health():
        logger.debug("Health check called")
        return {"status": "healthy"}

    # ── Playback WebSocket endpoint ────────────────────────────────────────
    @app.websocket("/ws/play/{play_id}")
    async def playback_ws_endpoint(websocket: WebSocket, play_id: str):
        logger.info(f"[PLAY WS] connection attempt for play_id: {play_id}")

        session = get_play_session(play_id)
        if not session:
            logger.warning(f"[PLAY WS] rejected: session {play_id} not found")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Play session not found")
            return

        await websocket.accept()
        await connection_manager.connect(play_id, websocket)
        logger.info(f"[PLAY WS] accepted for play_id: {play_id}")

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event_data = json.loads(data)
                    await playback_handler.handle_event(play_id, websocket, session, event_data)
                except json.JSONDecodeError as e:
                    await websocket.send_json({
                        "event_type": "ERROR",
                        "data": {"error": f"Invalid JSON: {e}"},
                    })

        except WebSocketDisconnect:
            logger.info(f"[PLAY WS] client disconnected from play_id: {play_id}")
            if session.task and not session.task.done():
                session.task.cancel()
            await connection_manager.disconnect(websocket)

        except Exception as e:
            logger.error(f"[PLAY WS] error for play_id {play_id}: {e}", exc_info=True)
            await connection_manager.disconnect(websocket)

    app.session_manager = session_manager
    app.browser_service = browser_service
    app.connection_manager = connection_manager
    app.websocket_handler = websocket_handler

    return app


# Create app instance for uvicorn
app = create_app()
