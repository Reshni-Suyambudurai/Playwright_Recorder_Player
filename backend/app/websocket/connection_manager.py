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
    
    Maintains:
      session_id -> List[WebSocket]           for broadcast support
      "session_id:client_id" -> WebSocket     for targeted per-client replies
    """
    
    def __init__(self):
        # session_id -> list of WebSocket connections (for broadcast)
        self._connections: Dict[str, List[WebSocket]] = {}
        # WebSocket -> session_id (reverse mapping for disconnect cleanup)
        self._connection_to_session: Dict[WebSocket, str] = {}
        # "session_id:client_id" -> WebSocket (for targeted send)
        self._client_connections: Dict[str, WebSocket] = {}
        # WebSocket -> client_id (reverse mapping for client cleanup)
        self._connection_to_client: Dict[WebSocket, str] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)
        self._connection_to_session[websocket] = session_id

    def register_client(self, session_id: str, client_id: str, websocket: WebSocket) -> None:
        """
        Bind a client_id to its WebSocket after HELLO handshake.
        Call this once the client has identified itself.
        """
        key = f"{session_id}:{client_id}"
        self._client_connections[key] = websocket
        self._connection_to_client[websocket] = client_id
    
    async def disconnect(self, websocket: WebSocket) -> None:
        if websocket not in self._connection_to_session:
            return
        
        session_id = self._connection_to_session.pop(websocket)
        
        if session_id in self._connections:
            self._connections[session_id].remove(websocket)
            if not self._connections[session_id]:
                del self._connections[session_id]

        # Clean up client mapping if registered
        client_id = self._connection_to_client.pop(websocket, None)
        if client_id:
            key = f"{session_id}:{client_id}"
            self._client_connections.pop(key, None)

    async def send_to_client(self, session_id: str, client_id: str, message: dict) -> bool:
        """
        Send a message to one specific client identified by session_id + client_id.
        Returns True if delivered, False if client not found.
        """
        key = f"{session_id}:{client_id}"
        websocket = self._client_connections.get(key)
        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            print(f"Error sending to client {key}: {e}")
            await self.disconnect(websocket)
            return False

    async def broadcast_to_session(self, session_id: str, message: dict) -> None:
        """Broadcast a message to all clients in a session."""
        if session_id not in self._connections:
            return
        
        disconnected = []
        for websocket in self._connections[session_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to {session_id}: {str(e)}")
                disconnected.append(websocket)
        
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
