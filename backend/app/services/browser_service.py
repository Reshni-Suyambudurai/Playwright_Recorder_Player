"""
BrowserService for managing Playwright browser operations.
"""
import base64
import logging
import time
from typing import Optional, Tuple, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("playwright_recorder.services.browser")

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


class BrowserService:
    """Manages browser lifecycle operations."""

    def __init__(self):
        self._playwright = None

    async def launch_browser(self, viewport_width: int = VIEWPORT_WIDTH, viewport_height: int = VIEWPORT_HEIGHT, headless: bool = True) -> Tuple[Browser, BrowserContext, Page]:
        """Launch a Playwright browser at the given viewport size."""
        t0 = time.perf_counter()
        logger.info(
            "[BROWSER START] launching Playwright browser headless=%s viewport=%sx%s",
            headless,
            viewport_width,
            viewport_height,
        )
        try:
            t_pw = time.perf_counter()
            self._playwright = await async_playwright().start()
            logger.info("[BROWSER START] async_playwright started in %dms", int((time.perf_counter() - t_pw) * 1000))

            t_launch = time.perf_counter()
            browser = await self._playwright.chromium.launch(headless=headless)
            logger.info("[BROWSER START] chromium launched in %dms", int((time.perf_counter() - t_launch) * 1000))

            t_context = time.perf_counter()
            browser_context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height}
            )
            logger.info("[BROWSER START] browser context created in %dms", int((time.perf_counter() - t_context) * 1000))

            t_page = time.perf_counter()
            page = await browser_context.new_page()
            logger.info(
                "[BROWSER START] first page created in %dms (total %dms)",
                int((time.perf_counter() - t_page) * 1000),
                int((time.perf_counter() - t0) * 1000),
            )

            return browser, browser_context, page

        except Exception as e:
            logger.error(
                "[BROWSER START] failed after %dms: %s",
                int((time.perf_counter() - t0) * 1000),
                e,
                exc_info=True,
            )
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            raise Exception(f"Failed to launch browser: {str(e)}")

    async def take_screenshot(self, page: Page) -> str:
        """Capture a screenshot of the current page and return as base64 data URI."""
        try:
            import time as _time
            t_cdp = _time.perf_counter()
            logger.debug(f"[SCREENSHOT] → sending CDP screenshot request to browser")
            png_bytes = await page.screenshot(
                type="jpeg",
                quality=60,
                full_page=False,
                clip={"x": 0, "y": 0, "width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                timeout=5000,  # 5-second cap — never hang on a navigating/loading page
            )
            t_cdp_done = _time.perf_counter()
            logger.debug(
                f"[SCREENSHOT] ← browser returned {len(png_bytes):,} bytes "
                f"in {int((t_cdp_done - t_cdp)*1000)}ms"
            )

            t_enc = _time.perf_counter()
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64}"
            logger.debug(
                f"[SCREENSHOT] base64 encode done in {int((_time.perf_counter()-t_enc)*1000)}ms "
                f"→ payload {len(data_uri):,} chars"
            )
            return data_uri
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            raise

    async def perform_click(self, page: Page, x: int, y: int, button: str = "left") -> None:
        """Perform a mouse click at the given viewport coordinates."""
        logger.info(f"Clicking at ({x}, {y}) button={button}")
        await page.mouse.click(x, y, button=button)

    async def perform_scroll(self, page: Page, x: int, y: int, delta_x: float, delta_y: float) -> None:
        """Move mouse to (x, y) then scroll by (delta_x, delta_y)."""
        logger.info(f"Scrolling at ({x},{y}) delta=({delta_x},{delta_y})")
        await page.mouse.move(x, y)
        await page.mouse.wheel(delta_x, delta_y)

    async def perform_type(self, page: Page, selector: dict, text: str) -> None:
        """Fill a form field using its selector. Uses occurrence_index to target
        the correct element when multiple elements share the same selector."""
        strategy = selector.get("strategy")
        value = selector.get("value")
        occurrence_index = selector.get("occurrence_index", 0)
        logger.info(f"Typing into {strategy}={value} [occurrence_index={occurrence_index}]")

        try:
            if occurrence_index > 0:
                # Multiple elements share this selector — locate by index
                if strategy == "id":
                    query = f"#{value}"
                elif strategy == "css":
                    query = value
                else:
                    # XPath: fall back to keyboard
                    await page.keyboard.type(text)
                    return

                elements = await page.query_selector_all(query)
                if occurrence_index < len(elements):
                    await elements[occurrence_index].fill(text)
                else:
                    logger.warning(f"occurrence_index {occurrence_index} out of range ({len(elements)} matches), using index 0")
                    await elements[0].fill(text)
            else:
                # Unique selector — use page.fill directly
                if strategy == "id":
                    await page.fill(f"#{value}", text)
                elif strategy == "css":
                    await page.fill(value, text)
                elif strategy == "xpath":
                    await page.fill(f"xpath={value}", text)
                else:
                    await page.keyboard.type(text)
        except Exception as e:
            logger.error(f"perform_type failed for {strategy}={value}: {e}")
            raise  # let caller handle — do not silently type into wrong element

    async def perform_key(self, page: Page, key: str) -> None:
        """Press a named key (Enter, Tab, Escape, etc.)."""
        logger.info(f"Pressing key: {key}")
        await page.keyboard.press(key)

    async def close_browser(self, browser: Optional[Browser]) -> None:
        """Close a browser instance."""
        logger.info("Closing browser")
        if browser is not None:
            try:
                await browser.close()
                logger.info("Browser closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

        if self._playwright is not None:
            try:
                await self._playwright.stop()
                self._playwright = None
                logger.info("Playwright stopped")
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")

    async def navigate_to_url(self, page: Optional[Page], url: str, timeout: int = 30000) -> Dict[str, Any]:
        """Navigate to a URL using Playwright page."""
        if page is None:
            raise Exception("Page instance is None")

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        logger.info(f"Navigating to: {url}")
        try:
            response = await page.goto(url, wait_until="load", timeout=timeout)
            # Best-effort wait for network to settle (JS-heavy SPAs finish rendering)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # timeout is fine — page is still usable after "load"
            title = await page.title()
            status_code = response.status if response else None
            logger.info(f"Navigation success: {url} | title={title} | status={status_code}")
            return {"success": True, "url": url, "title": title, "status_code": status_code}
        except Exception as e:
            logger.error(f"Navigation failed for {url}: {e}", exc_info=True)
            raise Exception(f"Navigation failed: {str(e)}")
