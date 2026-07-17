"""
WebSocket event definitions and schemas.

If BrowserService is the worker and WebSocketHandler is the controller, then this file is the dictionary that defines:

What messages can be sent
What data each message contains
The names of all WebSocket events

Think of it like an API specification.
It only defines the structure.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class HelloData(BaseModel):
    """Data for HELLO event."""
    client_id: str
    session_id: str


class PingData(BaseModel):
    """Data for PING event."""
    timestamp: datetime = Field(default_factory=datetime.now)


class PongData(BaseModel):
    """Data for PONG event."""
    timestamp: datetime
    received_timestamp: datetime = Field(default_factory=datetime.now)


class ErrorData(BaseModel):
    """Data for ERROR event."""
    error: str
    message: str


class WelcomeData(BaseModel):
    """Data for WELCOME event (server response to HELLO)."""
    session_id: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)


class WebSocketEvent(BaseModel):
    """Base WebSocket event."""
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class NavigateData(BaseModel):
    """Data for NAVIGATE event."""
    url: str


class NavigationSuccessData(BaseModel):
    """Data for NAVIGATION_SUCCESS event."""
    url: str
    title: Optional[str] = None
    status_code: Optional[int] = None


class NavigationErrorData(BaseModel):
    """Data for NAVIGATION_ERROR event."""
    url: str
    error: str
    message: str


class EventType:
    """Event type constants."""
    HELLO = "HELLO"
    PING = "PING"
    PONG = "PONG"
    WELCOME = "WELCOME"
    ERROR = "ERROR"
    NAVIGATE = "NAVIGATE"
    NAVIGATION_SUCCESS = "NAVIGATION_SUCCESS"
    NAVIGATION_ERROR = "NAVIGATION_ERROR"
    # Screenshot streaming
    START_RECORDING = "START_RECORDING"
    RECORDING_STARTED = "RECORDING_STARTED"
    FRAME = "FRAME"
    CLICK_ACTION = "CLICK_ACTION"
    ACTION_DONE = "ACTION_DONE"
    # Input overlay
    INPUT_DETECTED = "INPUT_DETECTED"
    TYPE_ACTION = "TYPE_ACTION"
    # Additional actions
    SCROLL_ACTION = "SCROLL_ACTION"
    KEY_ACTION = "KEY_ACTION"
    PAGE_REFRESH = "PAGE_REFRESH"
    PAGE_BACK = "PAGE_BACK"
    # Recording lifecycle
    STOP_RECORDING = "STOP_RECORDING"
    RECORDING_STOPPED = "RECORDING_STOPPED"
    # Tab management
    TAB_OPENED = "TAB_OPENED"
    SWITCH_TAB = "SWITCH_TAB"
    TAB_SWITCHED = "TAB_SWITCHED"
