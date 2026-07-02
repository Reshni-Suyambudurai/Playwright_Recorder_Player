"""
RecordingSession model for storing session data.
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime


class SessionStatus(Enum):
    """Session status enumeration."""
    ACTIVE = "active"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class RecordingSession:
    """
    Represents a single recording session.
    
    Stores all necessary information about a browser session including
    the browser instance, context, page, and session metadata.
    """
    session_id: str
    browser: Optional[object] = None
    browser_context: Optional[object] = None
    page: Optional[object] = None
    current_url: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    
    def is_active(self) -> bool:
        """Check if the session is currently active."""
        return self.status == SessionStatus.ACTIVE
    
    def stop(self) -> None:
        """Mark the session as stopped."""
        self.status = SessionStatus.STOPPED
    
    def set_error(self) -> None:
        """Mark the session as having an error."""
        self.status = SessionStatus.ERROR
