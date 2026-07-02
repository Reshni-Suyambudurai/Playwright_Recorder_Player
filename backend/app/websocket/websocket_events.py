"""
WebSocket event definitions and schemas.
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
