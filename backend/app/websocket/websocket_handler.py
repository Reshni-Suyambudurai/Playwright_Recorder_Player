"""
WebSocket event handler for routing and processing WebSocket events.
"""
from datetime import datetime
from typing import Dict, Any
from app.websocket.connection_manager import ConnectionManager
from app.websocket.websocket_events import EventType, HelloData, PongData, WelcomeData, ErrorData
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService


class WebSocketHandler:
    """
    Handles WebSocket events and routes them to appropriate handlers.
    """
    
    def __init__(self, connection_manager: ConnectionManager, session_manager: SessionManager, browser_service: BrowserService):
        """
        Initialize the WebSocket handler.
        
        Args:
            connection_manager: ConnectionManager instance for managing connections
            session_manager: SessionManager instance for session access
            browser_service: BrowserService instance for browser operations
        """
        self.connection_manager = connection_manager
        self.session_manager = session_manager
        self.browser_service = browser_service
    
    async def handle_hello(self, session_id: str, data: dict) -> dict:
        """
        Handle HELLO event from client.
        
        Validates that the session exists and responds with a welcome message.
        
        Args:
            session_id: The session ID
            data: Event data containing client_id
            
        Returns:
            Response message dict with WELCOME event
        """
        try:
            client_id = data.get("client_id")
            
            if not client_id:
                return self._error_response("INVALID_CLIENT_ID", "client_id is required in HELLO event")
            
            # Create welcome response
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
    
    async def handle_event(self, session_id: str, event_data: dict) -> dict:
        """
        Route incoming event to appropriate handler.
        
        Args:
            session_id: The session ID
            event_data: The event dict containing event_type and data
            
        Returns:
            Response message dict or None if no response needed
        """
        try:
            event_type = event_data.get("event_type")
            data = event_data.get("data", {})
            
            if not event_type:
                return self._error_response("NO_EVENT_TYPE", "event_type is required")
            
            # Route to appropriate handler
            if event_type == EventType.HELLO:
                return await self.handle_hello(session_id, data)
            
            elif event_type == EventType.PING:
                return await self.handle_ping(session_id, data)
            
            elif event_type == EventType.PONG:
                await self.handle_pong(session_id, data)
                return None  # No response for PONG
            
            elif event_type == EventType.NAVIGATE:
                return await self.handle_navigate(session_id, data)
            
            else:
                return self._error_response("UNKNOWN_EVENT", f"Unknown event type: {event_type}")
        
        except Exception as e:
            return self._error_response("EVENT_HANDLER_ERROR", str(e))
    
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
