"""
ScreenshotService — captures a Playwright page screenshot and sends it
as a FRAME event to a specific client over WebSocket.
"""
import logging
from datetime import datetime
from playwright.async_api import Page
from app.services.browser_service import BrowserService, VIEWPORT_WIDTH, VIEWPORT_HEIGHT
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger("playwright_recorder.services.screenshot")


class ScreenshotService:
    def __init__(self, browser_service: BrowserService, connection_manager: ConnectionManager):
        self._browser_service = browser_service
        self._connection_manager = connection_manager

    async def capture_and_send(self, page: Page, session_id: str, client_id: str) -> bool:
        """
        Take a screenshot of the current page state and push a FRAME event
        directly to the requesting client.
        Returns True on success, False on failure.
        """
        try:
            image_data = await self._browser_service.take_screenshot(page)
            frame_event = {
                "event_type": "FRAME",
                "data": {
                    "image": image_data,
                    "width": VIEWPORT_WIDTH,
                    "height": VIEWPORT_HEIGHT,
                    "timestamp": datetime.now().isoformat(),
                },
            }
            sent = await self._connection_manager.send_to_client(session_id, client_id, frame_event)
            if not sent:
                logger.warning(f"FRAME not delivered — client {client_id} not found in session {session_id}")
            return sent
        except Exception as e:
            logger.error(f"capture_and_send failed: {e}", exc_info=True)
            return False
