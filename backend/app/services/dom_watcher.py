"""
DomWatcher — pure event detector.

Attaches Playwright event listeners to a page and notifies CaptureManager
whenever the DOM changes.  All screenshot scheduling, debouncing, and
settle logic now lives in CaptureManager.
"""
import asyncio
import logging
from playwright.async_api import Page
try:
    from playwright._impl._errors import TargetClosedError
except ImportError:
    TargetClosedError = Exception  # fallback for older playwright versions
from app.services.capture_manager import CaptureReason as _CaptureReason

logger = logging.getLogger("playwright_recorder.services.dom_watcher")


class DomWatcher:
    def __init__(self, capture_manager):
        self._capture_manager = capture_manager
        self._page: Page | None = None
        self._active: bool = False

    async def attach(self, page: Page, session_id: str, client_id: str) -> None:
        """
        Attach DOM change listeners to the Playwright page.
        Call once after navigation has started.
        session_id and client_id are kept only for logging.
        """
        self._page = page
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

    async def detach(self) -> None:
        """Stop watching."""
        self._active = False
        logger.info(f"DomWatcher detached")

    # ── internal ──────────────────────────────────────────────────

    def _on_page_event(self, *_) -> None:
        """Sync Playwright event callback — delegates to CaptureManager."""
        if self._active and self._page:
            asyncio.ensure_future(
                self._capture_manager.request(self._page, _CaptureReason.DOM_MUTATION)
            )

    async def _on_dom_mutation(self, *_) -> None:
        """Called from JS MutationObserver via expose_function."""
        if self._active and self._page:
            await self._capture_manager.request(self._page, _CaptureReason.DOM_MUTATION)