"""
SessionManager for managing recording sessions.
"""
import logging
from typing import Optional, Dict, List
import uuid
from app.models.session import RecordingSession

logger = logging.getLogger("playwright_recorder.session_manager")


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
    
    async def cleanup_session(self, session_id: str) -> None:
        """
        Cleanup all Playwright resources for a session.
        
        Closes browser, context, and all pages in correct order.
        
        Args:
            session_id: The session ID to cleanup
        """
        session = self.get_session(session_id)
        if not session:
            return
        
        try:
            # Close all tab pages first
            for tab_id, page in list(session.tabs.items()):
                if page:
                    try:
                        await page.close()
                        logger.debug(f"Closed page for tab {tab_id} in session {session_id}")
                    except Exception as e:
                        logger.warning(f"Error closing tab {tab_id}: {e}")
            session.tabs.clear()
            
            # Close main page
            if session.page:
                try:
                    await session.page.close()
                    logger.debug(f"Closed main page in session {session_id}")
                    session.page = None
                except Exception as e:
                    logger.warning(f"Error closing main page: {e}")
            
            # Close browser context
            if session.browser_context:
                try:
                    await session.browser_context.close()
                    logger.debug(f"Closed browser context in session {session_id}")
                    session.browser_context = None
                except Exception as e:
                    logger.warning(f"Error closing browser context: {e}")
            
            # Close browser
            if session.browser:
                try:
                    await session.browser.close()
                    logger.debug(f"Closed browser in session {session_id}")
                    session.browser = None
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")
            
            # Remove session from dict
            self.remove_session(session_id)
            logger.info(f"Session {session_id} cleaned up and removed")
            
        except Exception as e:
            logger.error(f"Unexpected error during session cleanup {session_id}: {e}", exc_info=True)

