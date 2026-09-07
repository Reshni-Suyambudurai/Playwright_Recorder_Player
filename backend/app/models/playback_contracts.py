"""
Typed request/response and websocket payload contracts for playback.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StartPlaybackRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    recording_json: dict[str, Any] | None = None  # Full recording JSON from MCP
    steps: dict[str, list[list[dict[str, Any]]]] | None = None  # Recording steps (backward compat)
    source: str = "fastapi"                       # "fastapi" or "mcp"
    headless: bool = True                         # Browser headless mode
    capture_frames: bool = True                   # Capture frames for frontend


class StartPlaybackResponse(BaseModel):
    play_session_id: str


class StopPlaybackResponse(BaseModel):
    success: bool


class PlaybackEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class PlaybackHelloData(BaseModel):
    client_id: str


class PlaybackPauseClickData(BaseModel):
    x: float
    y: float


class PlaybackPauseScrollData(BaseModel):
    x: float = 0
    y: float = 0
    delta_y: float = 0


class PlaybackPauseTypeData(BaseModel):
    selector: dict[str, Any]
    text: str = ""


class PlaybackStepPatch(BaseModel):
    stepId: int
    shouldRun: bool | None = None
    pause: bool | None = None


class PlaybackPatchStepsData(BaseModel):
    patches: list[PlaybackStepPatch] = Field(default_factory=list)
