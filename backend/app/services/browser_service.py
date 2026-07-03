"""
BrowserService for managing Playwright browser operations.
"""
import base64
import logging
from typing import Optional, Tuple, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("playwright_recorder.services.browser")

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720


class BrowserService:
    """Manages browser lifecycle operations."""

    def __init__(self):
        self._playwright = None

    async def launch_browser(self) -> Tuple[Browser, BrowserContext, Page]:
        """Launch a Playwright browser with a fixed 1280×720 viewport."""
        logger.info("Launching Playwright browser")
        try:
            self._playwright = await async_playwright().start()
            browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Chromium browser launched")

            browser_context = await browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
            )
            page = await browser_context.new_page()
            logger.info(f"Browser context created with viewport {VIEWPORT_WIDTH}×{VIEWPORT_HEIGHT}")

            return browser, browser_context, page

        except Exception as e:
            logger.error(f"Failed to launch browser: {e}", exc_info=True)
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            raise Exception(f"Failed to launch browser: {str(e)}")

    async def take_screenshot(self, page: Page) -> str:
        """Capture a screenshot of the current page and return as base64 data URI."""
        try:
            png_bytes = await page.screenshot(
                type="jpeg",
                quality=75,
                full_page=False,
                clip={"x": 0, "y": 0, "width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            )
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            return f"data:image/jpeg;base64,{b64}"
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
        """Fill a form field using its selector. Falls back to keyboard if fill fails."""
        strategy = selector.get("strategy")
        value = selector.get("value")
        logger.info(f"Typing into {strategy}={value}")
        try:
            if strategy == "id":
                await page.fill(f"#{value}", text)
            elif strategy == "css":
                await page.fill(value, text)
            elif strategy == "xpath":
                await page.fill(f"xpath={value}", text)
            else:
                await page.keyboard.type(text)
        except Exception as e:
            logger.warning(f"fill() failed ({e}), falling back to keyboard.type()")
            await page.keyboard.type(text)

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
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            title = await page.title()
            status_code = response.status if response else None
            logger.info(f"Navigation success: {url} | title={title} | status={status_code}")
            return {"success": True, "url": url, "title": title, "status_code": status_code}
        except Exception as e:
            logger.error(f"Navigation failed for {url}: {e}", exc_info=True)
            raise Exception(f"Navigation failed: {str(e)}")

    
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
            logger.error("navigate_to_url called with None page")
            raise Exception("Page instance is None")

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        logger.info(f"Navigating to: {url}")
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            title = await page.title()
            status_code = response.status if response else None
            logger.info(f"Navigation success: {url} | title={title} | status={status_code}")

            return {
                "success": True,
                "url": url,
                "title": title,
                "status_code": status_code
            }

        except Exception as e:
            logger.error(f"Navigation failed for {url}: {e}", exc_info=True)
            raise Exception(f"Navigation failed: {str(e)}")
