"""
Snapshot Service for ARIA snapshot assertions.

Captures ARIA information from DOM elements within a specified rectangular region
and generates a descriptive ARIA snapshot for assertion validation.
"""
from typing import Any, Dict, Optional
from playwright.async_api import Page


class SnapshotService:
    """Service for capturing ARIA snapshots of DOM regions."""

    async def capture_aria_snapshot(
        self,
        page: Page,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> Dict[str, Any]:
        """
        Capture ARIA snapshot of DOM elements within the specified rectangle.

        Args:
            page: Playwright page object
            x: Top-left x coordinate in viewport
            y: Top-left y coordinate in viewport
            width: Rectangle width in pixels
            height: Rectangle height in pixels

        Returns:
            Dictionary with snapshot data:
            {
                'label': 'element label or description',
                'ariaSnapshot': 'formatted ARIA dump',
                'locator': 'best locator for the element',
                'elements': [{...}, ...]  # elements found in rectangle
            }
        """
        try:
            # Get all elements within the rectangle
            result = await page.evaluate(
                """
                ({ x, y, width, height }) => {
                    const elements = [];
                    const rect = { x, y, x2: x + width, y2: y + height };
                    
                    // Find all elements that intersect with the rectangle
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        const bounds = el.getBoundingClientRect();
                        
                        // Check intersection
                        if (bounds.left < rect.x2 && bounds.right > rect.x &&
                            bounds.top < rect.y2 && bounds.bottom > rect.y) {
                            
                            const ariaLabel = el.getAttribute('aria-label');
                            const ariaDescribed = el.getAttribute('aria-describedby');
                            const role = el.getAttribute('role') || el.tagName.toLowerCase();
                            const text = el.textContent?.trim().substring(0, 100) || '';
                            
                            elements.push({
                                tag: el.tagName.toLowerCase(),
                                text: text,
                                role: role,
                                ariaLabel: ariaLabel,
                                ariaDescribed: ariaDescribed,
                                id: el.id || '',
                                className: el.className || '',
                            });
                        }
                    }
                    
                    return {
                        count: elements.length,
                        elements: elements.slice(0, 5),  // Top 5 elements
                    };
                }
                """,
                {"x": x, "y": y, "width": width, "height": height},
            )

            # Find the best/largest element for the label
            label = "Selected region"
            aria_snapshot = self._generate_aria_snapshot(result["elements"])

            if result["elements"]:
                best_elem = result["elements"][0]
                if best_elem["text"]:
                    label = best_elem["text"][:50]
                elif best_elem["ariaLabel"]:
                    label = best_elem["ariaLabel"][:50]
                elif best_elem["role"]:
                    label = f"{best_elem['role']} element"

            return {
                "label": label,
                "ariaSnapshot": aria_snapshot,
                "elementCount": result["count"],
                "topElements": result["elements"],
            }

        except Exception as e:
            return {
                "label": "Error capturing snapshot",
                "ariaSnapshot": f"Failed to capture snapshot: {str(e)}",
                "error": str(e),
            }

    def _generate_aria_snapshot(self, elements: list) -> str:
        """
        Generate a formatted ARIA snapshot string from elements.

        Args:
            elements: List of element data dictionaries

        Returns:
            Formatted ARIA snapshot string
        """
        lines = ["ARIA Snapshot:", "=" * 40]

        if not elements:
            lines.append("No elements found in selected region")
        else:
            for i, elem in enumerate(elements, 1):
                lines.append(f"\n[{i}] {elem['tag'].upper()}")
                lines.append(f"    Role: {elem['role']}")
                if elem["text"]:
                    lines.append(f"    Text: {elem['text']}")
                if elem["ariaLabel"]:
                    lines.append(f"    Aria-Label: {elem['ariaLabel']}")
                if elem["id"]:
                    lines.append(f"    ID: {elem['id']}")

        lines.append("\n" + "=" * 40)
        return "\n".join(lines)
