"""Pydantic models for validation catalog and discovery payloads."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ValidationCondition(BaseModel):
    field: str
    op: str
    value: Any = None


class ValidationConditionSet(BaseModel):
    all_of: list[ValidationCondition] = Field(default_factory=list, alias="allOf")
    any_of: list[ValidationCondition] = Field(default_factory=list, alias="anyOf")

    model_config = {"populate_by_name": True}


class ValidationMatchRule(BaseModel):
    tag_names: list[str] = Field(default_factory=list, alias="tagNames")
    input_types: list[str] = Field(default_factory=list, alias="inputTypes")
    aria_roles: list[str] = Field(default_factory=list, alias="ariaRoles")
    attribute_hints: dict[str, list[Any]] = Field(default_factory=dict, alias="attributeHints")

    model_config = {"populate_by_name": True}


class ValidationOptionCatalog(BaseModel):
    key: str
    display_name: str = Field(alias="displayName")
    applies_when: ValidationConditionSet = Field(default_factory=ValidationConditionSet, alias="appliesWhen")
    description: Optional[str] = None

    model_config = {"populate_by_name": True}


class ValidationGroupCatalog(BaseModel):
    key: str
    display_name: str = Field(alias="displayName")
    options: list[ValidationOptionCatalog] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ValidationElementTypeCatalog(BaseModel):
    key: str
    display_name: str = Field(alias="displayName")
    match: ValidationMatchRule = Field(default_factory=ValidationMatchRule)
    validation_groups: list[ValidationGroupCatalog] = Field(default_factory=list, alias="validationGroups")

    model_config = {"populate_by_name": True}


class ValidationCatalog(BaseModel):
    catalog_version: str = Field(default="1.0.0", alias="catalogVersion")
    generated_at: Optional[str] = Field(default=None, alias="generatedAt")
    element_types: list[ValidationElementTypeCatalog] = Field(default_factory=list, alias="elementTypes")

    model_config = {"populate_by_name": True}


class BoundingRect(BaseModel):
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0


class ComputedStyleSnapshot(BaseModel):
    color: Optional[str] = None
    background_color: Optional[str] = Field(default=None, alias="backgroundColor")
    border_color: Optional[str] = Field(default=None, alias="borderColor")
    font_family: Optional[str] = Field(default=None, alias="fontFamily")

    model_config = {"populate_by_name": True}


class ValidationElementSnapshot(BaseModel):
    tag_name: str = Field(alias="tagName")
    type: Optional[str] = None
    input_type: Optional[str] = Field(default=None, alias="inputType")
    role: Optional[str] = None
    aria_role: Optional[str] = Field(default=None, alias="ariaRole")
    aria_label: Optional[str] = Field(default=None, alias="ariaLabel")
    aria_has_popup: Optional[bool] = Field(default=None, alias="ariaHasPopup")
    aria_modal: Optional[bool] = Field(default=None, alias="ariaModal")
    aria_live: Optional[str] = Field(default=None, alias="ariaLive")
    title: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    placeholder: Optional[str] = None
    value: Optional[str] = None
    current_value: Optional[str] = Field(default=None, alias="currentValue")
    text_content: Optional[str] = Field(default=None, alias="textContent")
    disabled: bool = False
    readonly: bool = False
    checked: bool = False
    required: bool = False
    multiple: bool = False
    hidden: bool = False
    visible: bool = True
    content_editable: bool = Field(default=False, alias="contentEditable")
    href: Optional[str] = None
    target: Optional[str] = None
    download: bool = False
    has_icon: bool = Field(default=False, alias="hasIcon")
    is_password: bool = Field(default=False, alias="isPassword")
    class_name: Optional[str] = Field(default=None, alias="className")
    bounding_rect: BoundingRect = Field(default_factory=BoundingRect, alias="boundingRect")
    computed_style: ComputedStyleSnapshot = Field(default_factory=ComputedStyleSnapshot, alias="computedStyle")
    selector: Optional[dict[str, Any]] = None

    model_config = {"populate_by_name": True}


class ValidationGroupResult(BaseModel):
    key: str
    display_name: str = Field(alias="displayName")
    options: list[ValidationOptionCatalog] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ValidationDiscoveryRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    x: Optional[float] = None
    y: Optional[float] = None
    selector: Optional[dict[str, Any]] = None

    model_config = {"populate_by_name": True}


class ValidationDiscoveryResponse(BaseModel):
    is_validatable: bool = Field(alias="isValidatable")
    element_category: Optional[str] = Field(default=None, alias="elementCategory")
    matched_catalog_keys: list[str] = Field(default_factory=list, alias="matchedCatalogKeys")
    element_snapshot: ValidationElementSnapshot = Field(alias="elementSnapshot")
    available_groups: list[ValidationGroupResult] = Field(default_factory=list, alias="availableGroups")

    model_config = {"populate_by_name": True}
