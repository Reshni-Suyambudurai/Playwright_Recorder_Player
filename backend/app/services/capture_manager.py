"""
CaptureManager — central screenshot coordinator.
The CaptureManager centralizes all screenshot requests and decides:

When to take a screenshot
Whether to wait before taking it
Whether to ignore duplicate requests
Whether to delay DOM updates
Whether to serialize multiple capture requests

Think of it as a traffic controller for screenshots.

Notice that CaptureManager never takes screenshots itself.

It only decides when ScreenshotService.capture_and_send() should be called.

One instance per browser/page session (recording or playback).
Never shared across unrelated sessions or clients.

Owns:
  - asyncio.Lock        — serialises all capture I/O
  - _dirty flag         — set by DOM mutations, cleared by the worker after capture
  - _worker_task        — single background loop polling dirty flag every DOM_POLL_MS
  - settle logic        — per-reason wait strategy

Priority model
  HIGH: ACTION_CLICK, ACTION_TYPE, ACTION_SCROLL, STEP_DONE,
        PAUSE_CLICK, PAUSE_SCROLL, PAUSE_TYPE, ERROR, MANUAL
        → acquire lock immediately, apply settle, take screenshot

  LOW: DOM_MUTATION
        → set _dirty = True only (zero tasks, zero lock contention)
        → worker polls every DOM_POLL_MS; if dirty: capture once, clear flag
"""
import asyncio
import logging
from enum import Enum

logger = logging.getLogger("playwright_recorder.services.capture_manager")

DOM_POLL_MS = 300  # Worker polling interval — max latency between a mutation and its frame


class CaptureReason(Enum):
    DOM_MUTATION  = "DOM-WATCHER"
    ACTION_CLICK  = "CLICK"
    ACTION_TYPE   = "TYPE"
    ACTION_SCROLL = "SCROLL"
    STEP_DONE     = "STEP"
    ERROR         = "ERROR"
    MANUAL        = "MANUAL"
    PAUSE_CLICK   = "PAUSE-CLICK"
    PAUSE_SCROLL  = "PAUSE-SCROLL"
    PAUSE_TYPE    = "PAUSE-TYPE"


class SettleStrategy(Enum):
    NONE          = "none"
    FIXED_DELAY   = "fixed"
    WAIT_FOR_NAV  = "nav"    # wait for domcontentloaded
    WAIT_FOR_IDLE = "idle"   # wait for networkidle


# Reasons that preempt pending DOM debounce tasks
_HIGH_PRIORITY = {
    CaptureReason.ACTION_CLICK,
    CaptureReason.ACTION_TYPE,
    CaptureReason.ACTION_SCROLL,
    CaptureReason.STEP_DONE,
    CaptureReason.ERROR,
    CaptureReason.MANUAL,
    CaptureReason.PAUSE_CLICK,
    CaptureReason.PAUSE_SCROLL,
    CaptureReason.PAUSE_TYPE,
}

# Default (settle_strategy, timeout_ms) per reason
_SETTLE_DEFAULTS: dict[CaptureReason, tuple[SettleStrategy, int]] = {
    CaptureReason.DOM_MUTATION:  (SettleStrategy.NONE,          0),
    CaptureReason.ACTION_CLICK:  (SettleStrategy.FIXED_DELAY,   300),
    CaptureReason.ACTION_TYPE:   (SettleStrategy.FIXED_DELAY,   300),
    CaptureReason.ACTION_SCROLL: (SettleStrategy.NONE,          0),
    CaptureReason.STEP_DONE:     (SettleStrategy.FIXED_DELAY,   300),
    CaptureReason.ERROR:         (SettleStrategy.NONE,          0),
    CaptureReason.MANUAL:        (SettleStrategy.NONE,          0),
    CaptureReason.PAUSE_CLICK:   (SettleStrategy.FIXED_DELAY,   300),
    CaptureReason.PAUSE_SCROLL:  (SettleStrategy.NONE,          0),
    CaptureReason.PAUSE_TYPE:    (SettleStrategy.FIXED_DELAY,   300),
}


class CaptureManager:
    """
    Central screenshot coordinator — one instance per browser/page session.
    """

    def __init__(self, screenshot_service, session_id: str, client_id: str):
        self._screenshot_service = screenshot_service
        self._session_id = session_id
        self._client_id  = client_id
        self._lock        = asyncio.Lock()
        # Dirty-flag worker state
        self._dirty: bool = False          # set by mutations, cleared by worker after capture
        self._page   = None                # page reference for the worker loop
        self._worker_task: asyncio.Task | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    def start_worker(self, page) -> None:
        """
        Launch the DOM capture worker loop.
        Called once by DomWatcher.attach() after the page is ready.
        Safe to call multiple times — only starts one worker.
        """
        self._page = page
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.ensure_future(self._dom_capture_worker())
            logger.info(f"[CAPTURE] DOM worker started (poll={DOM_POLL_MS}ms) session={self._session_id}")

    def stop(self) -> None:
        """
        Stop the DOM capture worker.
        Called by DomWatcher.detach() or session cleanup.
        """
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            logger.info(f"[CAPTURE] DOM worker stopped session={self._session_id}")
        self._worker_task = None
        self._dirty = False

    async def request(
        self,
        page,
        reason: CaptureReason,
        settle: SettleStrategy | None = None,
        settle_ms: int | None = None,
    ) -> bool:
        """
        Request a screenshot.

        HIGH-priority reasons acquire the lock immediately and capture.
        LOW-priority (DOM_MUTATION) just sets the dirty flag — the worker captures it.

        Args:
            page:      Playwright page object.
            reason:    Why this capture is being requested.
            settle:    Override the default SettleStrategy for this reason.
            settle_ms: Override the default timeout for the settle strategy.

        Returns True if a screenshot was sent (always True for DOM_MUTATION — async).
        """
        if reason in _HIGH_PRIORITY:
            # Clear dirty flag — worker should not double-capture what we're about to capture
            self._dirty = False
            return await self._capture_now(page, reason, settle, settle_ms)
        else:
            # DOM_MUTATION — just mark dirty; worker will capture at next poll tick
            self._dirty = True
            self._page  = page  # keep page reference fresh
            return True  # capture is scheduled via worker

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _dom_capture_worker(self) -> None:
        """
        Background loop: polls _dirty every DOM_POLL_MS.
        If dirty: clears flag, acquires lock, takes one screenshot.
        Structurally impossible to queue up multiple captures.
        """
        try:
            while True:
                await asyncio.sleep(DOM_POLL_MS / 1000)
                if self._dirty and self._page:
                    self._dirty = False
                    logger.debug("[CAPTURE][DOM-WATCHER] dirty flag set — capturing")
                    await self._capture_now(self._page, CaptureReason.DOM_MUTATION)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[CAPTURE] DOM worker crashed: {e}", exc_info=True)

    async def _capture_now(
        self,
        page,
        reason: CaptureReason,
        settle: SettleStrategy | None,
        settle_ms: int | None,
    ) -> bool:
        """Acquire the lock, apply settle strategy, take screenshot."""
        default_settle, default_ms = _SETTLE_DEFAULTS[reason]
        effective_settle = settle if settle is not None else default_settle
        effective_ms     = settle_ms if settle_ms is not None else default_ms
        caller           = reason.value

        async with self._lock:
            try:
                if effective_settle == SettleStrategy.WAIT_FOR_NAV:
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=effective_ms)
                        logger.info(f"[CAPTURE][{caller}] domcontentloaded settled")
                    except Exception:
                        await asyncio.sleep(0.3)
                        logger.info(f"[CAPTURE][{caller}] domcontentloaded timeout — 300ms fallback")

                elif effective_settle == SettleStrategy.WAIT_FOR_IDLE:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=effective_ms)
                        logger.info(f"[CAPTURE][{caller}] networkidle settled")
                    except Exception:
                        await asyncio.sleep(0.3)
                        logger.info(f"[CAPTURE][{caller}] networkidle timeout — 300ms fallback")

                elif effective_settle == SettleStrategy.FIXED_DELAY:
                    await asyncio.sleep(effective_ms / 1000)
                    logger.info(f"[CAPTURE][{caller}] fixed delay {effective_ms}ms done")

                ok = await self._screenshot_service.capture_and_send(
                    page, self._session_id, self._client_id, caller=caller
                )
                logger.info(f"[CAPTURE][{caller}] sent={ok}")

            except Exception as e:
                logger.error(f"[CAPTURE][{caller}] error: {e}", exc_info=True)
                return False

        # TODO Phase 2 — replace fixed settle with DOM stability detection:
        #   Option A: MutationObserver counter — wait until zero mutations for N ms
        #   Option B: perceptual hash comparison — recapture if hash differs after delay
        return ok
