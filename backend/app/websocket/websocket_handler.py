"""
WebSocket event handler for routing and processing WebSocket events.
"""
import asyncio
from datetime import datetime
from typing import Dict, Any
from app.websocket.connection_manager import ConnectionManager
from app.websocket.websocket_events import EventType, HelloData, PongData, WelcomeData, ErrorData
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService
from app.services.screenshot_service import ScreenshotService
from app.services.dom_watcher import DomWatcher


class WebSocketHandler:
    """
    Handles WebSocket events and routes them to appropriate handlers.
    """
    
    def __init__(self, connection_manager: ConnectionManager, session_manager: SessionManager,
                 browser_service: BrowserService, screenshot_service: ScreenshotService):
        self.connection_manager = connection_manager
        self.session_manager = session_manager
        self.browser_service = browser_service
        self.screenshot_service = screenshot_service
    
    async def handle_hello(self, session_id: str, websocket, data: dict) -> dict:
        """Handle HELLO — validates session, registers client_id mapping, replies WELCOME."""
        try:
            client_id = data.get("client_id")
            
            if not client_id:
                return self._error_response("INVALID_CLIENT_ID", "client_id is required in HELLO event")
            
            # Register the client_id → WebSocket mapping so future responses can be targeted
            self.connection_manager.register_client(session_id, client_id, websocket)
            
            welcome_data = {
                "session_id": session_id,
                "client_id": client_id,
                "message": "Connected to recording session",
                "timestamp": datetime.now().isoformat(),
                "connection_count": self.connection_manager.get_connection_count(session_id)
            }
            
            return {
                "event_type": EventType.WELCOME,
                "data": welcome_data,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return self._error_response("HELLO_ERROR", str(e))
    
    async def handle_ping(self, session_id: str, data: dict) -> dict:
        """
        Handle PING event from client.
        
        Responds with PONG event containing timestamps for latency measurement.
        
        Args:
            session_id: The session ID
            data: Event data (may contain client timestamp)
            
        Returns:
            Response message dict with PONG event
        """
        try:
            client_timestamp = data.get("timestamp")
            server_timestamp = datetime.now().isoformat()
            
            pong_data = {
                "client_timestamp": client_timestamp,
                "server_timestamp": server_timestamp,
                "received_at": server_timestamp
            }
            
            return {
                "event_type": EventType.PONG,
                "data": pong_data,
                "timestamp": server_timestamp
            }
        
        except Exception as e:
            return self._error_response("PING_ERROR", str(e))
    
    async def handle_pong(self, session_id: str, data: dict) -> None:
        """
        Handle PONG event from client.
        
        This is a client response to server ping. Just log and track.
        
        Args:
            session_id: The session ID
            data: Event data from client
        """
        try:
            client_timestamp = data.get("timestamp")
            server_received_at = datetime.now().isoformat()
            
            print(f"[{session_id}] PONG received - Client timestamp: {client_timestamp}, Server received at: {server_received_at}")
        
        except Exception as e:
            print(f"Error handling PONG: {str(e)}")
    
    async def handle_navigate(self, session_id: str, data: dict) -> dict:
        """
        Handle NAVIGATE event from client.
        
        Navigates the browser to the specified URL.
        
        Args:
            session_id: The session ID
            data: Event data containing url
            
        Returns:
            Response message dict with NAVIGATION_SUCCESS or NAVIGATION_ERROR
        """
        try:
            url = data.get("url")
            
            if not url:
                return self._error_response("INVALID_URL", "url is required in NAVIGATE event")
            
            # Get session from session manager
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._create_navigation_error(url, "SESSION_NOT_FOUND", "Session does not exist")
            
            # Get page from session
            if not session.page:
                return self._create_navigation_error(url, "NO_PAGE", "No active page in session")
            
            # Navigate to URL
            result = await self.browser_service.navigate_to_url(session.page, url)
            
            # Update session current_url
            session.current_url = result["url"]
            
            # Create success response
            return {
                "event_type": EventType.NAVIGATION_SUCCESS,
                "data": {
                    "url": result["url"],
                    "title": result.get("title"),
                    "status_code": result.get("status_code")
                },
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return self._create_navigation_error(data.get("url", "unknown"), "NAVIGATION_FAILED", str(e))
    
    async def handle_start_recording(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle START_RECORDING — navigate the browser, attach DomWatcher,
        take first screenshot and return RECORDING_STARTED.
        """
        try:
            url = data.get("url")
            recording_name = data.get("recording_name", "Untitled")

            if not url:
                return self._error_response("INVALID_URL", "url is required in START_RECORDING")

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            # Detach any existing watcher before starting fresh
            if session.dom_watcher:
                await session.dom_watcher.detach()

            # Navigate
            result = await self.browser_service.navigate_to_url(session.page, url)
            session.current_url = result["url"]

            # Attach DOM watcher — it will push frames on every change
            watcher = DomWatcher(self.screenshot_service)
            await watcher.attach(session.page, session_id, client_id)
            session.dom_watcher = watcher

            # Push the first frame immediately
            await self.screenshot_service.capture_and_send(session.page, session_id, client_id)

            return {
                "event_type": EventType.RECORDING_STARTED,
                "data": {
                    "recording_name": recording_name,
                    "url": result["url"],
                    "title": result.get("title"),
                    "timestamp": datetime.now().isoformat(),
                },
            }
        except Exception as e:
            return self._error_response("START_RECORDING_ERROR", str(e))

    async def handle_click_action(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle CLICK_ACTION — perform a mouse click in the Playwright page
        at the provided viewport coordinates and confirm with ACTION_DONE.
        The DomWatcher will automatically emit a new FRAME after DOM settles.
        """
        try:
            x = data.get("x")
            y = data.get("y")
            button = data.get("button", "left")

            if x is None or y is None:
                return self._error_response("INVALID_COORDS", "x and y are required in CLICK_ACTION")

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            await self.browser_service.perform_click(session.page, int(x), int(y), button)

            # Wait briefly for navigation / DOM updates to settle, then push a fresh frame.
            # The DomWatcher will also fire via load/mutation events, but this guarantees
            # at least one updated frame even when the MutationObserver misses a navigation.
            await asyncio.sleep(0.5)
            await self.screenshot_service.capture_and_send(session.page, session_id, client_id)

            return {
                "event_type": EventType.ACTION_DONE,
                "data": {"type": "click", "x": x, "y": y, "success": True},
            }
        except Exception as e:
            return self._error_response("CLICK_ACTION_ERROR", str(e))

    async def handle_event(self, session_id: str, websocket, event_data: dict) -> None:
        """
        Route incoming event to the appropriate handler and send the response
        directly to the originating client via client_id targeting.
        """
        try:
            event_type = event_data.get("event_type")
            client_id = event_data.get("client_id")   # top-level field on every event
            data = event_data.get("data", {})

            if not event_type:
                response = self._error_response("NO_EVENT_TYPE", "event_type is required")
            elif event_type == EventType.HELLO:
                response = await self.handle_hello(session_id, websocket, data)
            elif event_type == EventType.PING:
                response = await self.handle_ping(session_id, data)
            elif event_type == EventType.PONG:
                await self.handle_pong(session_id, data)
                return  # no response for PONG
            elif event_type == EventType.NAVIGATE:
                response = await self.handle_navigate(session_id, data)
            elif event_type == EventType.START_RECORDING:
                response = await self.handle_start_recording(session_id, client_id, data)
            elif event_type == EventType.CLICK_ACTION:
                response = await self.handle_click_action(session_id, client_id, data)
            else:
                response = self._error_response("UNKNOWN_EVENT", f"Unknown event type: {event_type}")

            if response:
                # Send to the specific client if we know their ID, else fall back to the socket
                if client_id:
                    sent = await self.connection_manager.send_to_client(session_id, client_id, response)
                    if not sent:
                        # client not registered yet (e.g. HELLO itself) — reply directly
                        await websocket.send_json(response)
                else:
                    await websocket.send_json(response)

        except Exception as e:
            error = self._error_response("EVENT_HANDLER_ERROR", str(e))
            await websocket.send_json(error)
    
    def _error_response(self, error_code: str, message: str) -> dict:
        """
        Create an error response.
        
        Args:
            error_code: Error code
            message: Error message
            
        Returns:
            Error response dict
        """
        return {
            "event_type": EventType.ERROR,
            "data": {
                "error": error_code,
                "message": message
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def _create_navigation_error(self, url: str, error_code: str, message: str) -> dict:
        """
        Create a navigation error response.
        
        Args:
            url: The URL that failed to navigate
            error_code: Error code
            message: Error message
            
        Returns:
            Navigation error response dict
        """
        return {
            "event_type": EventType.NAVIGATION_ERROR,
            "data": {
                "url": url,
                "error": error_code,
                "message": message
            },
            "timestamp": datetime.now().isoformat()
        }
