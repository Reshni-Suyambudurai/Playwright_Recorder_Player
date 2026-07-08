"""
PlaySession — in-memory model for a single playback run.
"""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class PlayStatus(Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    PAUSED   = "paused"
    DONE     = "done"
    ERROR    = "error"
    STOPPED  = "stopped"


@dataclass
class PlaySession:
    play_id: str
    recording_json: dict                      # full recording JSON sent by frontend

    # Playwright handles — set when browser launches
    browser: Optional[Any]  = None
    browser_context: Optional[Any] = None
    page: Optional[Any]     = None
    dom_watcher: Optional[Any] = None

    status: PlayStatus = PlayStatus.PENDING

    # asyncio event: awaited when a step has pause=True;
    # set by PLAY_RESUME from the client
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)

    # asyncio task running run_playback(); cancelled on PLAY_STOP
    task: Optional[asyncio.Task] = None

    # client tracking (set on HELLO)
    client_id: str = ""
