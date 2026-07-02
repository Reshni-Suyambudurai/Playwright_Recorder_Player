"""Recording models for action capture and replay"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class Viewport(BaseModel):
    """Viewport dimensions"""
    width: int = 1280
    height: int = 720
    deviceScaleFactor: float = 1.0


class Selector(BaseModel):
    """Element selector with strategy"""
    strategy: str = Field(..., description="Strategy: css, id, xpath, css-text")
    value: str = Field(..., description="Selector value")
    frameSelector: Optional[str] = None


class Coordinates(BaseModel):
    """X, Y coordinates"""
    x: int
    y: int


class Action(BaseModel):
    """Single action in recording"""
    id: int
    type: str  # NAVIGATE, CLICK, TYPE, SCROLL, WAIT, etc.
    url: Optional[str] = None
    coords: Optional[Coordinates] = None
    multiCoords: Optional[List[Coordinates]] = None
    prompt: Optional[str] = None
    text: Optional[str] = None  # For TYPE action
    pressEnter: Optional[bool] = None
    deltaY: Optional[int] = None  # For SCROLL action
    waitUntil: Optional[str] = None  # For NAVIGATE: load, domcontentloaded, networkidle
    waitAfterMs: Optional[int] = 100
    viewport: Viewport = Field(default_factory=Viewport)
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    label: Optional[str] = None  # Human-readable label
    description: Optional[str] = None
    isPassword: bool = False
    storeValue: bool = False
    selector: Optional[Selector] = None
    isTriggerNewTab: Optional[bool] = None
    shouldRun: bool = True
    required: bool = False
    tag: Optional[str] = None  # HTML tag (a, input, button, etc.)


class RecordingMetadata(BaseModel):
    """Recording metadata"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    createdAt: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    updatedAt: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    intent: str = ""


class Recording(BaseModel):
    """Complete recording with actions grouped by tabs"""
    version: str = "1.0"
    meta: RecordingMetadata
    steps: Dict[str, List[List[Action]]] = Field(default_factory=lambda: {"tab-1": []})

    class Config:
        json_schema_extra = {
            "example": {
                "version": "1.0",
                "meta": {
                    "id": "fc52b903-8924-4ad0-a59d-873e520ed749",
                    "title": "github login without password step",
                    "description": "",
                    "createdAt": 1782387934092,
                    "updatedAt": 1782387934092,
                    "intent": ""
                },
                "steps": {
                    "tab-1": [
                        [
                            {
                                "id": 1,
                                "type": "NAVIGATE",
                                "url": "https://github.com",
                                "coords": None,
                                "viewport": {"width": 1280, "height": 720, "deviceScaleFactor": 1.0}
                            }
                        ]
                    ]
                }
            }
        }


class SaveRecordingRequest(BaseModel):
    """Request to save recording"""
    recording: Recording
    title: str
    description: Optional[str] = ""
    intent: Optional[str] = ""
