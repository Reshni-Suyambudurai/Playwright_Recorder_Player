"""
Pydantic models for a Recording and its steps.
Schema matches the agreed JSON format.
"""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
import time


class SelectorInfo(BaseModel):
    strategy: str           # "id" | "css" | "xpath"
    value: str
    frame_selector: Optional[str] = None
    occurrence_index: int = 0  # 0-based index among all elements matching this selector


class Coords(BaseModel):
    x: int
    y: int


class Viewport(BaseModel):
    width: int = 1280
    height: int = 720
    device_scale_factor: float = Field(1.0, alias="deviceScaleFactor")

    model_config = {"populate_by_name": True}


class RecordingStep(BaseModel):
    id: int
    type: str
    url: Optional[str] = None
    page_url: Optional[str] = Field(None, alias="pageUrl")
    page_title: Optional[str] = Field(None, alias="pageTitle")
    coords: Optional[Coords] = None
    button: Optional[str] = None
    text: Optional[str] = None
    delta_x: Optional[float] = Field(None, alias="deltaX")
    delta_y: Optional[float] = Field(None, alias="deltaY")
    press_enter: Optional[bool] = Field(None, alias="pressEnter")
    wait_after_ms: Optional[int] = Field(None, alias="waitAfterMs")
    viewport: Optional[Viewport] = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    label: Optional[str] = None
    description: Optional[str] = None
    is_password: bool = Field(False, alias="isPassword")
    store_value: bool = Field(False, alias="storeValue")
    selector: Optional[SelectorInfo] = None
    is_trigger_new_tab: Optional[bool] = Field(None, alias="isTriggerNewTab")
    should_run: bool = Field(True, alias="shouldRun")
    required: bool = False
    tag: Optional[str] = None
    frame_index: int = Field(0, alias="frameIndex")
    # Internal only — not serialised to JSON output
    tab_id: str = Field("tab-1", exclude=True)

    model_config = {"populate_by_name": True}

    def to_json_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude={"tab_id"})


class RecordingMeta(BaseModel):
    id: str
    title: str
    description: str = ""
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000), alias="createdAt")
    updated_at: int = Field(default_factory=lambda: int(time.time() * 1000), alias="updatedAt")
    intent: str = ""

    model_config = {"populate_by_name": True}


class Recording(BaseModel):
    version: str = "1.0"
    meta: RecordingMeta
    # steps grouped by tab: { "tab-1": [[step1], [step2], ...] }
    steps: dict[str, list[list[dict]]] = Field(default_factory=lambda: {"tab-1": []})

    def add_step(self, step: RecordingStep) -> None:
        tab_key = step.tab_id or "tab-1"
        if tab_key not in self.steps:
            self.steps[tab_key] = []
        self.steps[tab_key].append([step.to_json_dict()])

    def step_count(self) -> int:
        return sum(len(group) for group in self.steps.get("tab-1", []))
