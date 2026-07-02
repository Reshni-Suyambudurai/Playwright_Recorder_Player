"""
BrowserService for managing Playwright browser operations.
"""
import logging
from typing import Optional, Tuple, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("playwright_recorder.services.browser")


class BrowserService:
    """Manages browser lifecycle operations."""

    def __init__(self):
        self._playwright = None

    async def launch_browser(self) -> Tuple[Browser, BrowserContext, Page]:
        """Launch a Playwright browser with context and page."""
        logger.info("Launching Playwright browser")
        try:
            self._playwright = await async_playwright().start()
            logger.debug("Playwright started")

            browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Chromium browser launched")

            browser_context = await browser.new_context()
            page = await browser_context.new_page()
            logger.info("Browser context and page created")

            return browser, browser_context, page

        except Exception as e:
            logger.error(f"Failed to launch browser: {e}", exc_info=True)
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
            raise Exception(f"Failed to launch browser: {str(e)}")
    
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
