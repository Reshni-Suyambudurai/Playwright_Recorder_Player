"""
PlaySession — in-memory model for a single playback run.
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from app.models.recording import RecordingStep


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

    # ✨ Pause-interrupted recording fields
    enable_pause_recording: bool = False  # Feature flag: capture pause actions
    captured_pause_steps: list[RecordingStep] = field(default_factory=list)  # Steps recorded during pause
    pause_step_insertion_points: dict[int, list[RecordingStep]] = field(default_factory=dict)  # {step_id: [steps added after]}
    original_recording_id: str | None = None  # Link to original recording
    paused_at_step_ids: list[int] = field(default_factory=list)  # Track all pause points

    def mark_pause_at_step(self, step_id: int) -> None:
        """Mark that a pause occurred after this step."""
        if step_id not in self.pause_step_insertion_points:
            self.pause_step_insertion_points[step_id] = []
        if step_id not in self.paused_at_step_ids:
            self.paused_at_step_ids.append(step_id)
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
