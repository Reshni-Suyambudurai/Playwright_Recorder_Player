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


class TargetMeta(BaseModel):
    tag: Optional[str] = None
    role: Optional[str] = None
    text: Optional[str] = None
    normalized_text: Optional[str] = Field(None, alias="normalizedText")
    aria_label: Optional[str] = Field(None, alias="ariaLabel")
    title: Optional[str] = None
    name: Optional[str] = None
    element_id: Optional[str] = Field(None, alias="id")
    data_test_id: Optional[str] = Field(None, alias="dataTestId")
    data_id: Optional[str] = Field(None, alias="dataId")
    data_cy: Optional[str] = Field(None, alias="dataCy")
    data_qa: Optional[str] = Field(None, alias="dataQa")
    class_hints: Optional[list[str]] = Field(None, alias="classHints")

    model_config = {"populate_by_name": True}


class Coords(BaseModel):
    x: int
    y: int


class Viewport(BaseModel):
    width: int = 1280
    height: int = 720
    device_scale_factor: float = Field(1.0, alias="deviceScaleFactor")

    model_config = {"populate_by_name": True}


class InputValidation(BaseModel):
    required: bool = False
    description: Optional[str] = None
    mode: Optional[str] = None
    min_length: Optional[int] = Field(None, alias="minLength")
    max_length: Optional[int] = Field(None, alias="maxLength")
    custom_regex: Optional[str] = Field(None, alias="customRegex")
    allow_negative_number: bool = Field(False, alias="allowNegativeNumber")

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
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    label: Optional[str] = None
    description: Optional[str] = None
    is_password: bool = Field(False, alias="isPassword")
    store_value: bool = Field(False, alias="storeValue")
    selector: Optional[SelectorInfo] = None
    target_meta: Optional[TargetMeta] = Field(None, alias="targetMeta")
    input_validation: Optional[InputValidation] = Field(None, alias="inputValidation")
    is_trigger_new_tab: Optional[bool] = Field(None, alias="isTriggerNewTab")
    should_run: bool = Field(True, alias="shouldRun")
    pause: bool = False
    frame_index: int = Field(0, alias="frameIndex")
    # Internal only — not serialised to JSON output
    tab_id: str = Field("tab-1", exclude=True)

    model_config = {"populate_by_name": True}

    def to_json_dict(self) -> dict:
        return self.model_dump(by_alias=True, exclude={"tab_id"})


class AssertionStep(BaseModel):
    """
    Represents an assertion step recorded during interactive assertion mode.
    
    Fields:
    - id: unique step ID
    - type: always "ASSERTION"
    - assertionType: "visibility" | "text" | "value" (the mode used)
    - selector: CSS/XPath selector for the target element
    - coords: (x, y) where hover occurred (for reference)
    - discoveredData: mode-specific extracted data
      - visibility: {visible, display, opacity}
      - text: {text, wordCount, charCount, accessibleName}
      - value: {value, type, dropdownOptions, optionCount}
    - pageUrl: URL of the page when assertion was captured
    - pageTitle: title of the page
    - timestamp: when assertion was captured
    - waitAfterMs: optional delay after assertion
    """
    id: int
    type: str = "ASSERTION"  # Always "ASSERTION"
    assertion_type: str = Field(alias="assertionType")  # "visibility" | "text" | "value"
    selector: Optional[SelectorInfo] = None
    coords: Optional[Coords] = None
    discovered_data: Optional[dict[str, Any]] = Field(None, alias="discoveredData")
    page_url: Optional[str] = Field(None, alias="pageUrl")
    page_title: Optional[str] = Field(None, alias="pageTitle")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    wait_after_ms: Optional[int] = Field(None, alias="waitAfterMs")
    label: Optional[str] = None
    should_run: bool = Field(True, alias="shouldRun")
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
    viewport: Viewport = Field(default_factory=Viewport)

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
