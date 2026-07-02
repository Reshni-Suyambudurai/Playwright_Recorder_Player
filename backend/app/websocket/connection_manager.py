"""
WebSocket connection manager for maintaining session-to-connection mappings.
"""
from typing import Dict, List, Optional
from fastapi import WebSocket
from app.websocket.websocket_events import WebSocketEvent, EventType
import json


class ConnectionManager:
    """
    Manages WebSocket connections and their mappings to sessions.
    
    Maintains a mapping of session_id -> List[WebSocket] to support
    multiple concurrent clients per session.
    """
    
    def __init__(self):
        """Initialize the connection manager."""
        # session_id -> list of WebSocket connections
        self._connections: Dict[str, List[WebSocket]] = {}
        # WebSocket -> session_id (reverse mapping for quick lookup)
        self._connection_to_session: Dict[WebSocket, str] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """
        Register a new WebSocket connection for a session.
        
        Args:
            session_id: The session ID to connect to
            websocket: The WebSocket connection
        """
        if session_id not in self._connections:
            self._connections[session_id] = []
        
        self._connections[session_id].append(websocket)
        self._connection_to_session[websocket] = session_id
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Unregister a WebSocket connection.
        
        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket not in self._connection_to_session:
            return
        
        session_id = self._connection_to_session[websocket]
        del self._connection_to_session[websocket]
        
        if session_id in self._connections:
            self._connections[session_id].remove(websocket)
            
            # Clean up empty session
            if not self._connections[session_id]:
                del self._connections[session_id]
    
    async def broadcast_to_session(self, session_id: str, message: dict) -> None:
        """
        Broadcast a message to all clients in a session.
        
        Args:
            session_id: The session ID to broadcast to
            message: The message to send
        """
        if session_id not in self._connections:
            return
        
        disconnected = []
        for websocket in self._connections[session_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to {session_id}: {str(e)}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected:
            await self.disconnect(websocket)
    
    async def broadcast_all(self, message: dict) -> None:
        """
        Broadcast a message to all connected clients across all sessions.
        
        Args:
            message: The message to send
        """
        for session_id in list(self._connections.keys()):
            await self.broadcast_to_session(session_id, message)
    
    def get_session_connections(self, session_id: str) -> List[WebSocket]:
        """
        Get all WebSocket connections for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            List of WebSocket connections for the session
        """
        return self._connections.get(session_id, [])
    
    def get_active_sessions(self) -> List[str]:
        """
        Get all session IDs with active connections.
        
        Returns:
            List of active session IDs
        """
        return list(self._connections.keys())
    
    def get_session_id(self, websocket: WebSocket) -> Optional[str]:
        """
        Get the session ID for a given WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            
        Returns:
            Session ID or None if not found
        """
        return self._connection_to_session.get(websocket)
    
    def get_connection_count(self, session_id: str) -> int:
        """
        Get the number of connected clients in a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            Number of connected clients
        """
        return len(self._connections.get(session_id, []))
    
    def get_total_connection_count(self) -> int:
        """
        Get the total number of connected clients across all sessions.
        
        Returns:
            Total number of connected clients
        """
        return sum(len(connections) for connections in self._connections.values())
