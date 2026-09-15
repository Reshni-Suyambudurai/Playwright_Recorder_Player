"""
Snapshot Service for ARIA snapshot assertions.

Uses Playwright's built-in page.accessibility.snapshot() to capture the accessibility tree
as a JSON-formatted string representing the page's DOM from an accessibility perspective.

Benefits:
- Clean, semantic tree structure (AXNode format)
- Follows W3C accessibility standards
- File size ~10-15KB (vs 50KB+ for HTML snapshots)
- Stable across CSS/visual changes
"""
import json
import time
from typing import Any, Dict
from playwright.async_api import Page


class SnapshotService:
    """Service for capturing full-page ARIA snapshots using Playwright's native method."""

    async def capture_aria_snapshot(
        self,
        page: Page,
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
    ) -> Dict[str, Any]:
        """
        Capture the full-page accessibility tree using Playwright's accessibility.snapshot().

        NOTE: x, y, width, height parameters are ignored. Full page is always captured.
              Region-based snapshots will be added in future versions.

        Args:
            page: Playwright page object
            x, y, width, height: (Deprecated - kept for backward compatibility)

        Returns:
            {
                'label': 'Descriptive label extracted from page title or main heading',
                'ariaSnapshot': 'JSON string representing the accessibility tree',
                'elementCount': Number of accessible nodes in the tree,
                'capturedAt': Unix timestamp,
                'captureMode': 'full-page'
            }
        """
        try:
            # Capture full-page accessibility tree using Playwright's accessibility API
            accessibility_tree = await page.accessibility.snapshot()

            # Convert tree to JSON string for storage and comparison
            aria_snapshot = json.dumps(accessibility_tree, indent=2)

            # Generate descriptive label from page title or first heading
            label = await self._generate_label(page)

            # Count accessible nodes (estimate from tree structure)
            element_count = self._count_nodes_from_tree(accessibility_tree)

            # Get current timestamp
            captured_at = int(time.time() * 1000)  # milliseconds

            return {
                "label": label,
                "ariaSnapshot": aria_snapshot,
                "elementCount": element_count,
                "capturedAt": captured_at,
                "captureMode": "full-page",
            }

        except Exception as e:
            return {
                "label": "Error",
                "ariaSnapshot": f"Error capturing ARIA snapshot: {str(e)}",
                "elementCount": 0,
                "capturedAt": int(time.time() * 1000),
                "captureMode": "full-page",
                "error": str(e),
            }

    async def _generate_label(self, page: Page) -> str:
        """Generate a descriptive label from page title or main heading."""
        try:
            # Try to get page title
            title = await page.title()
            if title and title.strip():
                return title[:100]

            # Fall back to first h1 if available
            h1_text = await page.locator("h1").first.text_content()
            if h1_text and h1_text.strip():
                return h1_text.strip()[:100]

            # Fall back to generic label
            return "Full-page ARIA snapshot"

        except Exception:
            return "ARIA snapshot"

    def _count_nodes_from_tree(self, tree: Any) -> int:
        """Count accessible nodes in the accessibility tree (AXNode structure)."""
        if not tree:
            return 0
        
        count = 1  # Count the root node
        
        # Recursively count child nodes
        if isinstance(tree, dict):
            children = tree.get('children', [])
            if isinstance(children, list):
                for child in children:
                    count += self._count_nodes_from_tree(child)
        
        return count
