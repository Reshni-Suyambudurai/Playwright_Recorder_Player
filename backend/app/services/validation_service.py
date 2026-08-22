"""Validation discovery service backed by validator.json."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Page

from app.models.validation import (
    ValidationCatalog,
    ValidationCondition,
    ValidationConditionSet,
    ValidationDiscoveryResponse,
    ValidationElementSnapshot,
    ValidationElementTypeCatalog,
    ValidationGroupCatalog,
    ValidationGroupResult,
    ValidationMatchRule,
    ValidationOptionCatalog,
)
from app.utils.selector_builder import _COLLECT_DROPDOWN_DATA_JS

logger = logging.getLogger("playwright_recorder.services.validation")


class ValidationService:
    def __init__(self, catalog_path: str | None = None):
        self._catalog_path = Path(catalog_path) if catalog_path else Path(__file__).resolve().parents[1] / "utils" / "validator.json"
        self._catalog_mtime: float | None = None
        self._catalog: ValidationCatalog | None = None

    def get_catalog(self) -> ValidationCatalog:
        try:
            mtime = self._catalog_path.stat().st_mtime
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Validation catalog not found: {self._catalog_path}") from exc

        if self._catalog is None or self._catalog_mtime != mtime:
            raw_text = self._catalog_path.read_text(encoding="utf-8")
            parsed = json.loads(raw_text)
            self._catalog = ValidationCatalog.model_validate(parsed)
            self._catalog_mtime = mtime
            logger.info("Validation catalog loaded from %s", self._catalog_path)

        return self._catalog

    async def discover_from_point(
        self,
        page: Page,
        x: float,
        y: float,
        *,
        wait_for_enrichment: bool = True,
    ) -> ValidationDiscoveryResponse:
        snapshot = await page.evaluate(_INSPECT_BY_POINT_JS, {"x": x, "y": y})
        if not snapshot:
            raise ValueError(f"No DOM element found at ({x}, {y})")

        if wait_for_enrichment:
            snapshot = await self._maybe_enrich_snapshot(page, x, y, snapshot)

        return self._discover_from_raw_snapshot(snapshot)

    async def _maybe_enrich_snapshot(
        self,
        page: Page,
        x: float,
        y: float,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        catalog = self.get_catalog()
        normalized = self._normalize_snapshot(snapshot)
        matches = self._match_catalog_entries(normalized, catalog)
        refresh = self._resolve_refresh_config(matches)

        if not refresh.get("enabled"):
            return snapshot

        max_attempts = max(int(refresh.get("max_attempts", 0) or 0), 0)
        interval_ms = max(int(refresh.get("interval_ms", 150) or 150), 50)

        current = snapshot
        for _ in range(max_attempts):
            if self._is_enrichment_ready(current, matches):
                return current

            await asyncio.sleep(interval_ms / 1000)
            refreshed = await page.evaluate(_INSPECT_BY_POINT_JS, {"x": x, "y": y})
            if refreshed:
                current = refreshed

        return current

    def _resolve_refresh_config(self, matches: list[Any]) -> dict[str, Any]:
        for entry in matches:
            refresh = entry.extraction.refresh
            if refresh.enabled and refresh.max_attempts > 0:
                return {
                    "enabled": True,
                    "max_attempts": refresh.max_attempts,
                    "interval_ms": refresh.interval_ms,
                }

        return {"enabled": False, "max_attempts": 0, "interval_ms": 0}

    def _is_enrichment_ready(self, snapshot: dict[str, Any], matches: list[Any]) -> bool:
        if not matches:
            return True

        for entry in matches:
            profile = (entry.extraction.extractor_profile or "").lower()
            if entry.key == "dropdown" or "dropdown" in profile:
                return self._snapshot_option_count(snapshot) > 0

        return True

    def _snapshot_option_count(self, snapshot: dict[str, Any]) -> int:
        options = snapshot.get("dropdownOptions")
        if isinstance(options, list):
            return len([value for value in options if isinstance(value, str) and value.strip()])

        count = snapshot.get("optionCount")
        try:
            return int(count)
        except (TypeError, ValueError):
            return 0

    async def discover_from_selector(self, page: Page, selector: dict[str, Any]) -> ValidationDiscoveryResponse:
        query = self._selector_to_query(selector)
        if not query:
            raise ValueError("selector is required for validation discovery")

        locator = page.locator(query)
        occurrence_index = int(selector.get("occurrence_index", 0) or 0)
        if occurrence_index > 0:
            locator = locator.nth(occurrence_index)

        snapshot = await locator.evaluate(_INSPECT_ELEMENT_JS)
        if not snapshot:
            raise ValueError("No DOM element matched the provided selector")

        snapshot["selector"] = selector
        return self._discover_from_raw_snapshot(snapshot)

    def _discover_from_raw_snapshot(self, raw_snapshot: dict[str, Any]) -> ValidationDiscoveryResponse:
        snapshot = self._normalize_snapshot(raw_snapshot)
        catalog = self.get_catalog()
        matches = self._match_catalog_entries(snapshot, catalog)

        available_groups: list[ValidationGroupResult] = []
        matched_keys: list[str] = []

        for entry in matches:
            matched_keys.append(entry.key)
            filtered_groups = self._filter_groups(snapshot, entry.validation_groups)
            available_groups.extend(filtered_groups)

        response = ValidationDiscoveryResponse(
            isValidatable=bool(available_groups),
            elementCategory=matches[0].display_name if matches else None,
            matchedCatalogKeys=matched_keys,
            elementSnapshot=snapshot,
            availableGroups=available_groups,
        )
        return response

    def _match_catalog_entries(self, snapshot: ValidationElementSnapshot, catalog: ValidationCatalog) -> list[Any]:
        scored_entries: list[tuple[int, int, int, Any]] = []
        for entry in catalog.element_types:
            score = self._score_entry(snapshot, entry.match)
            if score > 0:
                weighted_score = score + max(int(entry.match.priority or 0), 0)
                scored_entries.append((weighted_score, score, entry.match.priority, entry))

        scored_entries.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        if not scored_entries:
            return []

        best_weighted = scored_entries[0][0]
        best_raw = max(raw for weighted, raw, _, _ in scored_entries if weighted == best_weighted)
        best_priority = max(priority for weighted, raw, priority, _ in scored_entries if weighted == best_weighted and raw == best_raw)

        return [
            entry
            for weighted, raw, priority, entry in scored_entries
            if weighted == best_weighted and raw == best_raw and priority == best_priority
        ]

    def _score_entry(self, snapshot: ValidationElementSnapshot, match_rule: ValidationMatchRule) -> int:
        score = 0
        tag_name = snapshot.tag_name.lower()
        input_type = (snapshot.input_type or snapshot.type or "").lower()
        role = (snapshot.aria_role or snapshot.role or "").lower()

        if match_rule.tag_names and tag_name in {value.lower() for value in match_rule.tag_names}:
            score += 3
        if match_rule.input_types and input_type in {value.lower() for value in match_rule.input_types}:
            score += 3
        if match_rule.aria_roles and role in {value.lower() for value in match_rule.aria_roles}:
            score += 2

        for attr_name, expected_values in match_rule.attribute_hints.items():
            actual_value = self._get_snapshot_value(snapshot, attr_name)
            if actual_value is None:
                continue
            if self._value_matches_any(actual_value, expected_values):
                score += 1

        return score

    def _filter_groups(self, snapshot: ValidationElementSnapshot, groups: list[ValidationGroupCatalog]) -> list[ValidationGroupResult]:
        result: list[ValidationGroupResult] = []
        for group in groups:
            filtered_options = [option for option in group.options if self._condition_set_matches(snapshot, option.applies_when)]
            if filtered_options:
                result.append(
                    ValidationGroupResult(
                        key=group.key,
                        displayName=group.display_name,
                        options=filtered_options,
                    )
                )
        return result

    def _condition_set_matches(self, snapshot: ValidationElementSnapshot, conditions: ValidationConditionSet) -> bool:
        all_conditions_match = all(self._condition_matches(snapshot, condition) for condition in conditions.all_of)
        any_conditions_match = True
        if conditions.any_of:
            any_conditions_match = any(self._condition_matches(snapshot, condition) for condition in conditions.any_of)
        return all_conditions_match and any_conditions_match

    def _condition_matches(self, snapshot: ValidationElementSnapshot, condition: ValidationCondition) -> bool:
        actual_value = self._get_snapshot_value(snapshot, condition.field)
        op = condition.op.lower()
        expected_value = condition.value

        if op == "exists":
            return actual_value is not None and actual_value != "" and actual_value is not False
        if op == "eq":
            return self._normalize_value(actual_value) == self._normalize_value(expected_value)
        if op == "ne":
            return self._normalize_value(actual_value) != self._normalize_value(expected_value)
        if op == "in":
            if isinstance(expected_value, list):
                return self._normalize_value(actual_value) in {self._normalize_value(item) for item in expected_value}
            return False
        if op == "contains":
            actual_text = self._normalize_value(actual_value)
            expected_text = self._normalize_value(expected_value)
            return expected_text in actual_text
        if op == "gt":
            return self._as_float(actual_value) > self._as_float(expected_value)
        if op == "gte":
            return self._as_float(actual_value) >= self._as_float(expected_value)
        if op == "lt":
            return self._as_float(actual_value) < self._as_float(expected_value)
        if op == "lte":
            return self._as_float(actual_value) <= self._as_float(expected_value)

        logger.debug("Unknown validation operator '%s' for field '%s'", op, condition.field)
        return False

    def _selector_to_query(self, selector: dict[str, Any]) -> str | None:
        strategy = selector.get("strategy")
        value = selector.get("value")
        if not strategy or not value:
            return None

        if strategy == "id":
            return f"#{value}"
        if strategy == "css":
            return value
        if strategy == "xpath":
            return f"xpath={value}"
        return None

    def _normalize_snapshot(self, raw_snapshot: dict[str, Any]) -> ValidationElementSnapshot:
        tag_name = (raw_snapshot.get("tagName") or raw_snapshot.get("tag") or "").lower()
        input_type = raw_snapshot.get("inputType") or raw_snapshot.get("input_type")
        element_type = raw_snapshot.get("type") or input_type
        role = raw_snapshot.get("role")

        bounding_rect = raw_snapshot.get("boundingRect") or {}
        computed_style = raw_snapshot.get("computedStyle") or {}

        return ValidationElementSnapshot(
            tagName=tag_name,
            type=element_type,
            inputType=input_type,
            role=role,
            ariaRole=raw_snapshot.get("ariaRole") or role,
            ariaLabel=raw_snapshot.get("ariaLabel"),
            ariaHasPopup=self._as_bool(raw_snapshot.get("ariaHasPopup")),
            ariaModal=self._as_bool(raw_snapshot.get("ariaModal")),
            ariaLive=raw_snapshot.get("ariaLive"),
            title=raw_snapshot.get("title"),
            id=raw_snapshot.get("id"),
            name=raw_snapshot.get("name"),
            placeholder=raw_snapshot.get("placeholder"),
            value=raw_snapshot.get("value"),
            currentValue=raw_snapshot.get("currentValue"),
            selectedOption=raw_snapshot.get("selectedOption"),
            optionCount=raw_snapshot.get("optionCount"),
            dropdownOptions=raw_snapshot.get("dropdownOptions") or [],
            textContent=raw_snapshot.get("textContent"),
            disabled=self._as_bool(raw_snapshot.get("disabled")),
            readonly=self._as_bool(raw_snapshot.get("readonly")),
            checked=self._as_bool(raw_snapshot.get("checked")),
            required=self._as_bool(raw_snapshot.get("required")),
            multiple=self._as_bool(raw_snapshot.get("multiple")),
            hidden=self._as_bool(raw_snapshot.get("hidden")),
            visible=self._as_bool(raw_snapshot.get("visible", True)),
            contentEditable=self._as_bool(raw_snapshot.get("contentEditable")),
            href=raw_snapshot.get("href"),
            target=raw_snapshot.get("target"),
            download=self._as_bool(raw_snapshot.get("download")),
            hasIcon=self._as_bool(raw_snapshot.get("hasIcon")),
            isPassword=self._as_bool(raw_snapshot.get("isPassword")),
            className=raw_snapshot.get("className"),
            boundingRect=bounding_rect,
            computedStyle=computed_style,
            selector=raw_snapshot.get("selector"),
        )

    def _get_snapshot_value(self, snapshot: ValidationElementSnapshot, field_path: str) -> Any:
        lookup = {
            "tagName": snapshot.tag_name,
            "tag": snapshot.tag_name,
            "type": snapshot.type,
            "inputType": snapshot.input_type,
            "role": snapshot.role,
            "ariaRole": snapshot.aria_role,
            "ariarole": snapshot.aria_role,
            "ariaLabel": snapshot.aria_label,
            "arialabel": snapshot.aria_label,
            "ariaHasPopup": snapshot.aria_has_popup,
            "ariahaspopup": snapshot.aria_has_popup,
            "ariaModal": snapshot.aria_modal,
            "ariamodal": snapshot.aria_modal,
            "ariaLive": snapshot.aria_live,
            "arialive": snapshot.aria_live,
            "title": snapshot.title,
            "id": snapshot.id,
            "name": snapshot.name,
            "placeholder": snapshot.placeholder,
            "value": snapshot.value,
            "currentValue": snapshot.current_value,
            "selectedOption": snapshot.selected_option,
            "optionCount": snapshot.option_count,
            "dropdownOptions": snapshot.dropdown_options,
            "textContent": snapshot.text_content,
            "disabled": snapshot.disabled,
            "readonly": snapshot.readonly,
            "checked": snapshot.checked,
            "required": snapshot.required,
            "multiple": snapshot.multiple,
            "hidden": snapshot.hidden,
            "visible": snapshot.visible,
            "contentEditable": snapshot.content_editable,
            "contenteditable": snapshot.content_editable,
            "href": snapshot.href,
            "target": snapshot.target,
            "download": snapshot.download,
            "hasIcon": snapshot.has_icon,
            "hasicon": snapshot.has_icon,
            "isPassword": snapshot.is_password,
            "className": snapshot.class_name,
            "classname": snapshot.class_name,
            "boundingRect": snapshot.bounding_rect.model_dump(by_alias=True),
            "computedStyle": snapshot.computed_style.model_dump(by_alias=True),
        }

        current: Any = lookup
        for part in field_path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _value_matches_any(self, actual_value: Any, expected_values: list[Any]) -> bool:
        actual_normalized = self._normalize_value(actual_value)
        for expected_value in expected_values:
            if actual_normalized == self._normalize_value(expected_value):
                return True
        return False

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return value

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return bool(value)

    def _as_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def _build_snapshot_from_element_js() -> str:
    return r"""
(element) => {
    if (!element) return null;

    %s

    function isVisible(node) {
        const style = window.getComputedStyle(node);
        if (!style) return true;
        const rect = node.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    }

    const rect = element.getBoundingClientRect();
    const tagName = element.tagName.toLowerCase();
    const inputType = (element.getAttribute('type') || '').toLowerCase() || null;
    const role = element.getAttribute('role');
    const ariaLabel = element.getAttribute('aria-label');
    const ariaHasPopup = element.getAttribute('aria-haspopup');
    const ariaModal = element.getAttribute('aria-modal');
    const ariaLive = element.getAttribute('aria-live');
    const title = element.getAttribute('title');
    const placeholder = element.getAttribute('placeholder');
    const className = typeof element.className === 'string' ? element.className : String(element.className || '');
    const hasIcon = !!element.querySelector('svg, img, i, [data-icon], [aria-hidden="true"]');
    const label = ariaLabel || placeholder || title || null;
    const value = typeof element.value === 'string' ? element.value : null;
    const textContent = normalizeText(element.textContent || '');
    const computedStyle = window.getComputedStyle(element);
    const download = element.hasAttribute('download');

    const dropdownData = collectDropdownData(element);

    const snapshot = {
        tagName,
        type: inputType || tagName,
        inputType,
        role,
        ariaRole: role,
        ariaLabel,
        ariaHasPopup: ariaHasPopup === null ? null : ariaHasPopup !== 'false',
        ariaModal: ariaModal === null ? null : ariaModal !== 'false',
        ariaLive,
        title,
        id: element.id || null,
        name: element.getAttribute('name'),
        placeholder,
        value,
        currentValue: value !== null ? value : textContent,
        selectedOption: dropdownData.selectedOption,
        optionCount: dropdownData.optionCount,
        dropdownOptions: dropdownData.dropdownOptions,
        textContent,
        disabled: !!(element.disabled || element.getAttribute('aria-disabled') === 'true'),
        readonly: !!(element.readOnly || element.getAttribute('aria-readonly') === 'true'),
        checked: !!element.checked,
        required: !!(element.required || element.getAttribute('aria-required') === 'true'),
        multiple: !!element.multiple,
        hidden: !isVisible(element),
        visible: isVisible(element),
        contentEditable: element.isContentEditable || element.getAttribute('contenteditable') === 'true',
        href: element.getAttribute('href'),
        target: element.getAttribute('target'),
        download,
        hasIcon,
        isPassword: inputType === 'password',
        className: className || null,
        boundingRect: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
        },
        computedStyle: {
            color: computedStyle.color,
            backgroundColor: computedStyle.backgroundColor,
            borderColor: computedStyle.borderColor,
            fontFamily: computedStyle.fontFamily,
        },
    };

    return snapshot;
}
""" % _COLLECT_DROPDOWN_DATA_JS


def _build_snapshot_from_point_js() -> str:
    return r"""
(args) => {
    const { x, y } = args;
    const hit = document.elementFromPoint(x, y);
    if (!hit) return null;

        const semanticAncestor = hit.closest('[role="combobox"], [role="listbox"], select, [aria-haspopup="listbox"]');
        const semanticDescendant = hit.querySelector
            ? hit.querySelector('[role="combobox"], [role="listbox"], select, [aria-haspopup="listbox"]')
            : null;
        const semanticTarget = semanticAncestor
            || semanticDescendant
            || hit.closest('input, textarea, button, a, label')
            || hit;

    return (%s)(semanticTarget);
}
""" % _build_snapshot_from_element_js()


_INSPECT_ELEMENT_JS = _build_snapshot_from_element_js()
_INSPECT_BY_POINT_JS = _build_snapshot_from_point_js()
