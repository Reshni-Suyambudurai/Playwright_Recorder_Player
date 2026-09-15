"""
PlaySession — in-memory model for a single playback run.
"""
import asyncio
import time
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
    capture_manager: Optional[Any] = None  # CaptureManager — per-session

    status: PlayStatus = PlayStatus.PENDING

    # asyncio event: awaited when a step has pause=True;
    # set by PLAY_RESUME from the client
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)

    # asyncio task running run_playback(); cancelled on PLAY_STOP
    task: Optional[asyncio.Task] = None

    # client tracking (set on HELLO)
    client_id: str = ""

    # lifecycle timestamps used for in-memory session TTL cleanup
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    # ✨ MCP-related fields for event enrichment and optimization
    source: str = "fastapi"                   # "fastapi" or "mcp"
    capture_frames: bool = True               # Skip frame capture for MCP clients to save bandwidth
    headless: bool = True                     # Browser headless mode (False for MCP headed mode)
    total_steps: int = 0                      # Total steps in recording
    current_step_index: int = 0               # Current step index (0-based)
    current_step_id: int = 0                  # Current step ID (1-based)
    playback_start_time: float | None = None  # When playback started

    def get_elapsed_seconds(self) -> float:
        """Get total elapsed time since playback started"""
        if not self.playback_start_time:
            return 0.0
        return time.time() - self.playback_start_time

    def get_progress_percent(self) -> int:
        """Get progress as percentage (0-100)"""
        if self.total_steps == 0:
            return 0
        return int((self.current_step_index / self.total_steps) * 100)

    def touch(self) -> None:
        self.last_accessed_at = time.time()

    def mark_finished(self) -> None:
        self.finished_at = time.time()
        self.last_accessed_at = self.finished_at
