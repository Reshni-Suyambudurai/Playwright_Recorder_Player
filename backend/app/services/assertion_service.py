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

from app.utils.selector_builder import discover_by_assertion_mode

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
            mode: 'visibility' | 'text' | 'value'
            
        Returns:
            Filtered dict with mode-specific fields + selector
        """
        try:
            raw = await discover_by_assertion_mode(page, x, y, mode)
            if not raw:
                raise ValueError(f"No DOM element found at ({x}, {y})")

            if mode == "visibility":
                return self._extract_visibility(raw)
            elif mode == "text":
                return self._extract_text(raw)
            elif mode == "value":
                return self._extract_value(raw)
            else:
                raise ValueError(f"Unknown assertion mode: {mode}")

        except Exception as e:
            logger.error(f"Assertion discovery failed at ({x}, {y}) mode={mode}: {e}")
            raise

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
        Extract value-only fields (includes dropdown options if applicable).
        
        Returns: { mode, value, type, dropdownOptions, optionCount, selector }
        """
        options = raw.get("dropdownOptions", [])
        return {
            "mode": "value",
            "value": raw.get("value", ""),
            "type": raw.get("type", "unknown"),
            "dropdownOptions": options,
            "optionCount": len(options) if options else 0,
            "selector": raw.get("selector"),
        }
