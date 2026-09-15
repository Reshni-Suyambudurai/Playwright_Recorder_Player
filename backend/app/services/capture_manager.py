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
import time
from enum import Enum

logger = logging.getLogger("playwright_recorder.services.capture_manager")

DOM_POLL_MS = 300  # Worker polling interval — max latency between a mutation and its frame
MAX_BURST_FRAMES = 4  # max consecutive DOM-driven frames sent per unbroken mutation burst
QUIET_MS_BASE = 900   # base quiet window (~3 poll ticks) before a burst is considered over
QUIET_MS_MAX = 8000    # cap on the escalating quiet window — never wait longer than this
RAPID_RECUR_S = 2.0    # a burst restarting within this long after the last one ended counts as "rapid"


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
        self._burst_count = 0              # DOM-watcher frames sent so far in the current unbroken burst
        self._last_dirty_at: float = 0.0   # monotonic time of the last dirty signal seen
        self._burst_index = 0              # session-wide count of bursts started (for log tracking)
        self._total_dom_frames = 0         # session-wide count of DOM-watcher frames sent (for log tracking)
        self._last_burst_ended_at: float = 0.0  # monotonic time the previous burst ended, 0.0 if none yet
        self._rapid_streak = 0             # consecutive bursts that restarted within RAPID_RECUR_S
        self._quiet_ms_current: float = QUIET_MS_BASE  # current required quiet window, escalates on rapid recurrence
        self._wake_event = asyncio.Event()  # allows high-priority actions to wake worker immediately

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
        self._burst_count = 0
        self._last_dirty_at = 0.0
        self._burst_index = 0
        self._total_dom_frames = 0
        self._last_burst_ended_at = 0.0
        self._rapid_streak = 0
        self._quiet_ms_current = QUIET_MS_BASE
        self._wake_event.clear()

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
            # Keep dirty signal intact; action frame must be followed by DOM frame if page changed.
            result = await self._capture_now(page, reason, settle, settle_ms)
            self._page = page
            # Wake worker now instead of waiting up to DOM_POLL_MS for next tick.
            self._wake_event.set()
            return result
        else:
            # DOM_MUTATION — just mark dirty; worker will capture at next poll tick
            self._dirty = True
            self._page  = page  # keep page reference fresh
            return True  # capture is scheduled via worker

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _dom_capture_worker(self) -> None:
        """
        Background loop: polls _dirty every DOM_POLL_MS.

        Caps consecutive DOM-driven captures at MAX_BURST_FRAMES per unbroken
        mutation burst — a continuously-changing page (animations, polling
        widgets, chat) would otherwise get a screenshot on nearly every poll
        tick indefinitely. Once the cap is hit, further dirty ticks are
        skipped entirely until the page has been quiet for a sustained
        quiet window (not just one lucky poll tick — continuous churn has
        small natural lulls that a single-tick check would misread as
        "settled" and restart a fresh burst far too early). Once truly quiet,
        one last frame captures the settled state and the burst counter resets.

        Escalating backoff: if a page is periodic (a burst keeps restarting
        within RAPID_RECUR_S of the previous one ending — a clock, ticker,
        polling widget, etc.), the required quiet window doubles each time,
        up to QUIET_MS_MAX. This makes such a page taper down to progressively
        rarer bursts instead of producing a fresh capped burst forever. A
        burst that restarts slowly (the page genuinely calmed down for a
        while) resets the window back to QUIET_MS_BASE.
        """
        try:
            while True:
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=DOM_POLL_MS / 1000)
                except asyncio.TimeoutError:
                    pass
                self._wake_event.clear()
                if self._dirty and self._page:
                    self._dirty = False
                    self._last_dirty_at = time.monotonic()
                    if self._burst_count == 0:
                        self._burst_index += 1
                        if self._last_burst_ended_at:
                            gap_s = self._last_dirty_at - self._last_burst_ended_at
                            if gap_s < RAPID_RECUR_S:
                                self._rapid_streak += 1
                                self._quiet_ms_current = min(
                                    QUIET_MS_BASE * (2 ** self._rapid_streak), QUIET_MS_MAX
                                )
                            else:
                                self._rapid_streak = 0
                                self._quiet_ms_current = QUIET_MS_BASE
                            gap = f"{gap_s:.1f}s since last burst ended, quiet window now {self._quiet_ms_current:.0f}ms"
                        else:
                            gap = "first burst this session"
                        logger.info(f"[CAPTURE][DOM-WATCHER] burst #{self._burst_index} started ({gap})")
                    if self._burst_count < MAX_BURST_FRAMES:
                        self._burst_count += 1
                        self._total_dom_frames += 1
                        logger.debug(
                            f"[CAPTURE][DOM-WATCHER] dirty flag set — capturing "
                            f"({self._burst_count}/{MAX_BURST_FRAMES}, session total={self._total_dom_frames})"
                        )
                        await self._capture_now(self._page, CaptureReason.DOM_MUTATION)
                    else:
                        logger.debug("[CAPTURE][DOM-WATCHER] burst cap reached — skipping capture")
                elif self._burst_count > 0 and self._page:
                    if time.monotonic() - self._last_dirty_at >= self._quiet_ms_current / 1000:
                        # Sustained quiet — the burst is genuinely over.
                        self._total_dom_frames += 1
                        logger.info(
                            f"[CAPTURE][DOM-WATCHER] burst #{self._burst_index} ended — "
                            f"{self._burst_count} progress frame(s) + 1 final "
                            f"(session total={self._total_dom_frames})"
                        )
                        await self._capture_now(self._page, CaptureReason.DOM_MUTATION)
                        self._burst_count = 0
                        self._last_burst_ended_at = time.monotonic()
                    # else: still within the grace window — page may still be mid-churn, wait
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[CAPTURE] DOM worker crashed: {e}", exc_info=True)

    async def _capture_now(
        self,
        page,
        reason: CaptureReason,
        settle: SettleStrategy | None = None,
        settle_ms: int | None = None,
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
