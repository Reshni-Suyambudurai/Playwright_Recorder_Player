"""
Main entry point for the Playwright Recorder backend application.
"""
import logging
import os
import sys
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService
from app.api.recording import create_recording_router
from app.websocket.connection_manager import ConnectionManager
from app.websocket.websocket_handler import WebSocketHandler

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
    app = FastAPI(title="Playwright Recorder API", version="1.0.0")

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
    websocket_handler = WebSocketHandler(connection_manager, session_manager, browser_service)
    logger.info("All services initialized")

    # Register routers
    recording_router = create_recording_router(session_manager, browser_service)
    app.include_router(recording_router, prefix="/recording")
    logger.info("Recording router registered at /recording")

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
                    response = await websocket_handler.handle_event(session_id, event_data)
                    if response:
                        logger.debug(f"[WS] Sending to {session_id}: {response}")
                        await websocket.send_json(response)

                except json.JSONDecodeError as e:
                    logger.error(f"[WS] JSON decode error for session {session_id}: {e}")
                    error_response = websocket_handler._error_response(
                        "JSON_DECODE_ERROR",
                        f"Invalid JSON: {str(e)}"
                    )
                    await websocket.send_json(error_response)

        except WebSocketDisconnect:
            logger.info(f"[WS] Client disconnected from session {session_id}")
            await connection_manager.disconnect(websocket)

        except Exception as e:
            logger.error(f"[WS] Unexpected error in session {session_id}: {e}", exc_info=True)
            await connection_manager.disconnect(websocket)

    @app.get("/health")
    async def health():
        logger.debug("Health check called")
        return {"status": "healthy"}

    app.session_manager = session_manager
    app.browser_service = browser_service
    app.connection_manager = connection_manager
    app.websocket_handler = websocket_handler

    return app


# Create app instance for uvicorn
app = create_app()
