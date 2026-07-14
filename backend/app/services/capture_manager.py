"""
CaptureManager — central screenshot coordinator.

One instance per browser/page session (recording or playback).
Never shared across unrelated sessions or clients.

Owns:
  - asyncio.Lock       — serialises all capture I/O
  - _pending_dom task  — debounce handle for DOM_MUTATION events
  - settle logic       — per-reason wait strategy

Priority model
  HIGH: ACTION_CLICK, ACTION_TYPE, ACTION_SCROLL, STEP_DONE,
        PAUSE_CLICK, PAUSE_SCROLL, PAUSE_TYPE, ERROR, MANUAL
  LOW:  DOM_MUTATION

A HIGH request cancels any pending LOW debounce task before acquiring the lock.
"""
import asyncio
import logging
from enum import Enum

logger = logging.getLogger("playwright_recorder.services.capture_manager")

DEBOUNCE_MS = 300  # DOM_MUTATION debounce window


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
    CaptureReason.ACTION_CLICK:  (SettleStrategy.WAIT_FOR_NAV,  2000),
    CaptureReason.ACTION_TYPE:   (SettleStrategy.FIXED_DELAY,   300),
    CaptureReason.ACTION_SCROLL: (SettleStrategy.NONE,          0),
    CaptureReason.STEP_DONE:     (SettleStrategy.WAIT_FOR_IDLE, 2000),
    CaptureReason.ERROR:         (SettleStrategy.NONE,          0),
    CaptureReason.MANUAL:        (SettleStrategy.NONE,          0),
    CaptureReason.PAUSE_CLICK:   (SettleStrategy.WAIT_FOR_IDLE, 2000),
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
        self._pending_dom: asyncio.Task | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    async def request(
        self,
        page,
        reason: CaptureReason,
        settle: SettleStrategy | None = None,
        settle_ms: int | None = None,
    ) -> bool:
        """
        Request a screenshot.

        HIGH-priority reasons cancel any pending DOM debounce then capture immediately.
        LOW-priority (DOM_MUTATION) requests are debounced by DEBOUNCE_MS.

        Args:
            page:      Playwright page object.
            reason:    Why this capture is being requested.
            settle:    Override the default SettleStrategy for this reason.
            settle_ms: Override the default timeout for the settle strategy.

        Returns True if a screenshot was successfully sent.
        """
        if reason in _HIGH_PRIORITY:
            self._cancel_pending_dom()
            return await self._capture_now(page, reason, settle, settle_ms)
        else:
            # LOW priority — debounce
            self._cancel_pending_dom()
            self._pending_dom = asyncio.ensure_future(
                self._debounced_dom(page, reason, settle, settle_ms)
            )
            return True  # not yet captured, but scheduled

    # ── Internal helpers ───────────────────────────────────────────────────

    def _cancel_pending_dom(self) -> None:
        if self._pending_dom and not self._pending_dom.done():
            self._pending_dom.cancel()
            logger.debug("[CAPTURE] pending DOM capture cancelled (higher-priority action)")
        self._pending_dom = None

    async def _debounced_dom(
        self,
        page,
        reason: CaptureReason,
        settle: SettleStrategy | None,
        settle_ms: int | None,
    ) -> None:
        try:
            await asyncio.sleep(DEBOUNCE_MS / 1000)
            await self._capture_now(page, reason, settle, settle_ms)
        except asyncio.CancelledError:
            pass

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

        # DOM_MUTATION: 1.2s follow-up outside the lock (lets other captures run during sleep)
        if reason == CaptureReason.DOM_MUTATION:
            await asyncio.sleep(1.2)
            if page:
                async with self._lock:
                    try:
                        await self._screenshot_service.capture_and_send(
                            page, self._session_id, self._client_id,
                            caller="DOM-WATCHER-FOLLOWUP"
                        )
                        logger.info("[CAPTURE][DOM-WATCHER-FOLLOWUP] follow-up frame sent")
                    except Exception as e:
                        logger.warning(f"[CAPTURE][DOM-WATCHER-FOLLOWUP] error: {e}")

        return ok
