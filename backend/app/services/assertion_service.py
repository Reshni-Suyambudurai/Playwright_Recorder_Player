"""
AssertionService — Handles assertion discovery and extraction for visibility, text, and value modes.

Assertion modes:
- visibility: captures isVisible, display CSS, opacity
- text: captures textContent, word/char counts, accessible name
- value: captures current value, type, dropdown options (for selects)

Each mode extracts specific data from the raw DOM snapshot returned by discover_by_assertion_mode.
"""
import logging
from typing import Any, Optional
from playwright.async_api import Page

from app.utils.selector_builder import discover_by_assertion_mode, discover_assertion_data_from_element

logger = logging.getLogger("playwright_recorder.services.assertion")


class AssertionService:
    """
    Manages assertion discovery and extraction.
    
    Reuses discover_by_assertion_mode from selector_builder to capture
    all DOM data in one pass, then filters based on assertion mode.
    """

    async def discover_by_mode(
        self,
        page: Page,
        x: float,
        y: float,
        mode: str,
    ) -> dict[str, Any]:
        """
        Main entry point: inspect element at (x, y) and extract assertion data.
        
        Args:
            page: Playwright page
            x: viewport x coordinate
            y: viewport y coordinate
            mode: 'visibility' | 'text' | 'value' | 'snapshot'
            
        Returns:
            Filtered dict with mode-specific fields + selector
        """
        try:
            # Snapshot mode uses rectangle-based discovery via SnapshotService, not hover-based
            if mode == "snapshot":
                raise ValueError("Snapshot mode does not support hover-based discovery. Use rectangle-based discovery instead.")

            raw = await discover_by_assertion_mode(page, x, y, mode)
            if not raw:
                raise ValueError(f"No DOM element found at ({x}, {y})")

            return self._filter_by_mode(raw, mode)

        except Exception as e:
            logger.error(f"Assertion discovery failed at ({x}, {y}) mode={mode}: {e}")
            raise

    async def discover_from_element(self, element, mode: str) -> dict[str, Any]:
        """
        Same extraction as discover_by_mode, but reads directly from an already-resolved
        element handle instead of hit-testing a pixel coordinate. This is what playback uses:
        once the recorded selector has found the right element, there's no need (and no
        safe way, for large container elements) to re-locate it by coordinates.
        """
        try:
            if mode == "snapshot":
                raise ValueError("Snapshot mode does not support element-based discovery. Use rectangle-based discovery instead.")

            raw = await discover_assertion_data_from_element(element, mode)
            if not raw:
                raise ValueError("Element evaluation returned no data")

            return self._filter_by_mode(raw, mode)

        except Exception as e:
            logger.error(f"Assertion discovery from element failed mode={mode}: {e}")
            raise

    def _filter_by_mode(self, raw: dict[str, Any], mode: str) -> dict[str, Any]:
        if mode == "visibility":
            return self._extract_visibility(raw)
        elif mode == "text":
            return self._extract_text(raw)
        elif mode == "value":
            return self._extract_value(raw)
        else:
            raise ValueError(f"Unknown assertion mode: {mode}")

    def _extract_visibility(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Extract visibility-only fields.
        
        Returns: { mode, visible, display, opacity, selector }
        """
        return {
            "mode": "visibility",
            "visible": raw.get("visible", False),
            "display": raw.get("display", "unknown"),
            "opacity": raw.get("opacity", 1.0),
            "selector": raw.get("selector"),
        }

    def _extract_text(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Extract text-only fields.
        
        Returns: { mode, text, wordCount, charCount, accessibleName, selector }
        """
        text = raw.get("text", "")
        return {
            "mode": "text",
            "text": text,
            "wordCount": len(text.split()) if text else 0,
            "charCount": len(text),
            "accessibleName": raw.get("accessibleName", ""),
            "selector": raw.get("selector"),
        }

    def _extract_value(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Extract value-only fields (includes dropdown options for native <select> AND
        ARIA combobox/listbox widgets — see collectDropdownData in selector_builder.py).

        Returns: { mode, value, type, dropdownOptions, selectedOption, optionCount, selector }
        """
        options = raw.get("dropdownOptions", [])
        return {
            "mode": "value",
            "value": raw.get("value", ""),
            "type": raw.get("type", "unknown"),
            "dropdownOptions": options,
            "selectedOption": raw.get("selectedOption"),
            "optionCount": len(options) if options else 0,
            "selector": raw.get("selector"),
        }

    def compare_aria_snapshots(self, expected_yaml: str, actual_yaml: str) -> tuple[bool, str]:
        """
        Compare two ARIA snapshots (both in JSON format from page.accessibility.snapshot()).
        
        Uses line-by-line normalized comparison:
        - Strips whitespace from each line
        - Ignores empty lines
        - Counts differences
        
        Args:
            expected_yaml: JSON string captured at record time
            actual_yaml: JSON string captured during playback
            
        Returns:
            (passed: bool, reason: str)
            - passed=True if snapshots match (reason="")
            - passed=False with reason describing differences
        """
        def normalize_json(json_str: str) -> list[str]:
            """Normalize JSON by stripping each line and removing blanks."""
            if not json_str:
                return []
            return [line.strip() for line in json_str.strip().split('\n') if line.strip()]

        expected_lines = normalize_json(expected_yaml)
        actual_lines = normalize_json(actual_yaml)

        # Check if snapshots are identical
        if expected_lines == actual_lines:
            return True, ""

        # Count differences for error message
        diff_count = 0
        
        # Count line differences in overlapping range
        for exp, act in zip(expected_lines, actual_lines):
            if exp != act:
                diff_count += 1
        
        # Add difference if line counts differ
        diff_count += abs(len(expected_lines) - len(actual_lines))

        reason = f"ARIA snapshot mismatch: {diff_count} line(s) differ. " \
                 f"Expected {len(expected_lines)} lines, got {len(actual_lines)} lines."
        
        return False, reason
