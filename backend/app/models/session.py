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
    """
    session_id: str
    browser: Optional[object] = None
    browser_context: Optional[object] = None
    page: Optional[object] = None
    dom_watcher: Optional[object] = None   # DomWatcher — detached on disconnect
    capture_manager: Optional[object] = None  # CaptureManager — per-session screenshot coordinator
    current_url: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    # Recording state
    recording_id: str = ""
    recording_name: str = ""
    recording_description: str = ""
    recording_intent: str = ""
    recording_steps: list = field(default_factory=list)
    # Tab state — keyed by tab_id ("tab-1", "tab-2", ...)
    tabs: dict = field(default_factory=dict)          # tab_id → Page
    active_tab_id: str = ""
    tab_watchers: dict = field(default_factory=dict)  # tab_id → DomWatcher
    tab_meta: dict = field(default_factory=dict)      # tab_id → {title, url}
    
    def is_active(self) -> bool:
        """Check if the session is currently active."""
        return self.status == SessionStatus.ACTIVE
    
    def stop(self) -> None:
        """Mark the session as stopped."""
        self.status = SessionStatus.STOPPED
    
    def set_error(self) -> None:
        """Mark the session as having an error."""
        self.status = SessionStatus.ERROR
