"""
ScreenshotService — captures a Playwright page screenshot and sends it
as a FRAME event to a specific client over WebSocket.
"""
import logging
import time
from datetime import datetime
from playwright.async_api import Page
from app.services.browser_service import BrowserService, VIEWPORT_WIDTH, VIEWPORT_HEIGHT
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger("playwright_recorder.services.screenshot")


class ScreenshotService:
    def __init__(self, browser_service: BrowserService, connection_manager: ConnectionManager):
        self._browser_service = browser_service
        self._connection_manager = connection_manager

    async def capture_and_send(self, page: Page, session_id: str, client_id: str, caller: str = "?") -> bool:
        """
        Take a screenshot of the current page state and push a FRAME event
        directly to the requesting client.
        Returns True on success, False on failure.
        """
        t0 = time.perf_counter()
        logger.info(f"[▶ SCREENSHOT][{caller}] capture requested")
        try:
            # ── Stage 1: CDP round-trip + base64 encode (inside take_screenshot) ──
            image_data = await self._browser_service.take_screenshot(page)
            t_snap = int((time.perf_counter() - t0) * 1000)
            logger.info(
                f"[▶ SCREENSHOT][{caller}] browser→encode done in {t_snap}ms "
                f"(payload {len(image_data):,} chars)"
            )

            # ── Stage 2: build WS frame event ────────────────────────────────────
            frame_event = {
                "event_type": "FRAME",
                "data": {
                    "image": image_data,
                    "width": VIEWPORT_WIDTH,
                    "height": VIEWPORT_HEIGHT,
                    "timestamp": datetime.now().isoformat(),
                    "source": caller,
                },
            }

            # ── Stage 3: WebSocket send to UI ─────────────────────────────────────
            t_ws = time.perf_counter()
            logger.info(f"[▶ SCREENSHOT][{caller}] → sending FRAME over WebSocket")
            sent = await self._connection_manager.send_to_client(session_id, client_id, frame_event)
            t_ws_done = int((time.perf_counter() - t_ws) * 1000)
            t_total   = int((time.perf_counter() - t0)   * 1000)

            if sent:
                logger.info(
                    f"[✅ FRAME SENT][{caller}] "
                    f"ws_send={t_ws_done}ms  total={t_total}ms"
                )
            else:
                logger.warning(
                    f"[❌ FRAME FAILED][{caller}] client {client_id} not found "
                    f"(total={t_total}ms)"
                )
            return sent
        except Exception as e:
            logger.error(f"[❌ SCREENSHOT ERROR][{caller}] {e}", exc_info=True)
            return False
