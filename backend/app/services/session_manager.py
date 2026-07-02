"""
SessionManager for managing recording sessions.
"""
from typing import Optional, Dict, List
import uuid
from app.models.session import RecordingSession


class SessionManager:
    """
    Manages recording sessions lifecycle.
    
    Responsibilities:
    - Creating new sessions
    - Retrieving existing sessions
    - Removing sessions
    - Listing active sessions
    """
    
    def __init__(self):
        """Initialize the session manager with an empty sessions store."""
        self._sessions: Dict[str, RecordingSession] = {}
    
    def create_session(self) -> RecordingSession:
        """
        Create a new recording session.
        
        Returns:
            RecordingSession: Newly created session
        """
        session_id = str(uuid.uuid4())
        session = RecordingSession(session_id=session_id)
        self._sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[RecordingSession]:
        """
        Retrieve a session by ID.
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            RecordingSession if found, None otherwise
        """
        return self._sessions.get(session_id)
    
    def remove_session(self, session_id: str) -> bool:
        """
        Remove a session by ID.
        
        Args:
            session_id: The session ID to remove
            
        Returns:
            bool: True if session was removed, False if not found
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def list_active_sessions(self) -> List[RecordingSession]:
        """
        List all active sessions.
        
        Returns:
            List of active recording sessions
        """
        return [session for session in self._sessions.values() if session.is_active()]
    
    def list_all_sessions(self) -> List[RecordingSession]:
        """
        List all sessions regardless of status.
        
        Returns:
            List of all recording sessions
        """
        return list(self._sessions.values())
