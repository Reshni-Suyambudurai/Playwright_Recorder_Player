"""
DomWatcher — attaches Playwright event listeners to a page and emits a new
FRAME screenshot whenever the DOM changes (navigation, load, network idle).

Uses asyncio debouncing so rapid DOM mutations produce at most one frame
per DEBOUNCE_MS window rather than flooding the WebSocket.
"""
import asyncio
import logging
import time
from playwright.async_api import Page
try:
    from playwright._impl._errors import TargetClosedError
except ImportError:
    TargetClosedError = Exception  # fallback for older playwright versions
from app.services.screenshot_service import ScreenshotService

logger = logging.getLogger("playwright_recorder.services.dom_watcher")

DEBOUNCE_MS = 300   # wait this many ms after last change before capturing


class DomWatcher:
    def __init__(self, screenshot_service: ScreenshotService):
        self._screenshot_service = screenshot_service
        self._debounce_task: asyncio.Task | None = None
        self._page: Page | None = None
        self._session_id: str = ""
        self._client_id: str = ""
        self._active: bool = False
        self._in_flight: bool = False  # prevent screenshot flooding from rapid mutations

    async def attach(self, page: Page, session_id: str, client_id: str) -> None:
        """
        Attach DOM change listeners to the Playwright page.
        Call once after navigation has started.
        """
        self._page = page
        self._session_id = session_id
        self._client_id = client_id
        self._active = True

        # Fired on every full page navigation / reload
        page.on("load", self._on_page_event)
        # Fired when DOM is ready (before images/scripts finish)
        page.on("domcontentloaded", self._on_page_event)

        # Inject a MutationObserver into the page that calls back into Python
        # whenever the DOM tree changes (e.g. SPA route changes, dynamic content)
        await page.expose_function("__domChanged__", self._on_dom_mutation)

        _OBSERVER_SCRIPT = """
            (() => {
                if (window.__domObserverAttached__) return;
                window.__domObserverAttached__ = true;
                const observer = new MutationObserver(() => {
                    if (window.__domChanged__) window.__domChanged__();
                });
                observer.observe(document.documentElement, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    characterData: false,
                });
            })();
        """

        # add_init_script runs on every future navigation — covers SPA + full navigations
        await page.add_init_script(_OBSERVER_SCRIPT)
        # Also inject immediately into the already-loaded current page
        try:
            await page.evaluate(_OBSERVER_SCRIPT)
        except Exception:
            pass  # page may be navigating, init_script covers next load
        logger.info(f"DomWatcher attached to session {session_id}")

    def suppress_external(self, value: bool) -> None:
        """
        Called by _bg_screenshot to mark that an action screenshot is in flight.
        While True, DomWatcher will back off and reschedule instead of capturing.
        """
        self._in_flight = value
        if value:
            logger.info("[⏸ DOM-WATCHER] suppressed by action screenshot")
        else:
            logger.info("[▶ DOM-WATCHER] suppression lifted")

    async def detach(self) -> None:
        """Stop watching and cancel any pending debounce task."""
        self._active = False
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        logger.info(f"DomWatcher detached from session {self._session_id}")

    # ── internal ──────────────────────────────────────────────────

    def _on_page_event(self, *_) -> None:
        """Sync Playwright event callback — schedules async capture."""
        if self._active:
            asyncio.ensure_future(self._schedule_capture())

    async def _on_dom_mutation(self, *_) -> None:
        """Called from JS MutationObserver via expose_function."""
        if self._active:
            await self._schedule_capture()

    async def _schedule_capture(self) -> None:
        """Debounce: cancel pending task and reschedule."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.ensure_future(self._debounced_capture())

    async def _debounced_capture(self) -> None:
        try:
            await asyncio.sleep(DEBOUNCE_MS / 1000)
            # Re-check after sleep — detach() may have fired during the wait
            if not self._active or not self._page:
                return
            # Skip if a screenshot is already in progress — reschedule once it clears
            if self._in_flight:
                await asyncio.sleep(0.6)
                if self._active and not self._in_flight:
                    await self._schedule_capture()
                return
            logger.info("[⏳ DOM-WATCHER] debounce done — waiting for load...")
            t0 = time.perf_counter()
            try:
                await self._page.wait_for_load_state("load", timeout=5000)
                logger.info(f"[⏳ DOM-WATCHER] load in {int((time.perf_counter()-t0)*1000)}ms")
            except TargetClosedError:
                self._active = False
                return
            except Exception:
                logger.info(f"[⏳ DOM-WATCHER] load timeout after {int((time.perf_counter()-t0)*1000)}ms — proceeding")
            if not self._active or not self._page:
                return
            self._in_flight = True
            try:
                await self._screenshot_service.capture_and_send(
                    self._page, self._session_id, self._client_id, caller="DOM-WATCHER"
                )
                # Follow-up frame after 1.2s to catch lazy-loaded / embedded content
                await asyncio.sleep(1.2)
                if self._active and self._page:
                    logger.info("[⏳ DOM-WATCHER] sending follow-up frame (lazy content)")
                    await self._screenshot_service.capture_and_send(
                        self._page, self._session_id, self._client_id, caller="DOM-WATCHER-FOLLOWUP"
                    )
            except TargetClosedError:
                self._active = False
            finally:
                self._in_flight = False
        except asyncio.CancelledError:
            pass
        except TargetClosedError:
            self._active = False
        except Exception as e:
            logger.error(f"[❌ DOM-WATCHER] capture error: {e}")