"""
PlaybackService — executes a recorded JSON step-by-step in a Playwright browser,
streaming FRAME events and playback lifecycle events to the frontend.

Reuses: BrowserService, ScreenshotService, DomWatcher from the recording stack.
"""
import asyncio
import json
import logging
from typing import Any

from app.models.playback import PlaySession, PlayStatus
from app.services.browser_service import BrowserService
from app.services.screenshot_service import ScreenshotService
from app.services.dom_watcher import DomWatcher
from app.services.capture_manager import CaptureManager, CaptureReason, SettleStrategy
from app.utils.selector_builder import build_selector
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger("playwright_recorder.services.playback")

# ─── Event type constants for playback ─────────────────────────────────────
PLAY_STEP_START   = "PLAY_STEP_START"
PLAY_STEP_SKIPPED = "PLAY_STEP_SKIPPED"
PLAY_STEP_ERROR   = "PLAY_STEP_ERROR"   # non-fatal: step failed, playback continues
PLAY_PAUSED       = "PLAY_PAUSED"
PLAY_DONE         = "PLAY_DONE"
PLAY_ERROR        = "PLAY_ERROR"
FRAME             = "FRAME"


class PlaybackService:
    def __init__(
        self,
        browser_service: BrowserService,
        screenshot_service: ScreenshotService,
        connection_manager: ConnectionManager,
    ):
        self._browser_service   = browser_service
        self._screenshot_service = screenshot_service
        self._connection_manager = connection_manager
        # Dispatch table: step type → handler method
        # Add new step types here without touching _execute_step
        self._STEP_HANDLERS = {
            "NAVIGATE": self._step_navigate,
            "CLICK":    self._step_click,
            "TYPE":     self._step_type,
            "SCROLL":   self._step_scroll,
            "KEY":      self._step_key,
        }

    # ─── Public entry point ────────────────────────────────────────────────
    async def run_playback(
        self,
        session: PlaySession,
        play_id: str,
        client_id: str,
    ) -> None:
        """
        Main playback coroutine. Launched as an asyncio task by PlaybackHandler.
        Streams PLAY_* and FRAME events back to the client over WebSocket.
        """
        session.status = PlayStatus.RUNNING
        recording = session.recording_json
        meta   = recording.get("meta", {})
        steps_by_tab = recording.get("steps", {})

        # Use viewport from meta (may fall back to 1280×720)
        vp = meta.get("viewport", {})
        vp_width  = vp.get("width",  1280)
        vp_height = vp.get("height", 720)

        # Flatten steps from all tabs preserving tab order
        all_steps = []
        for tab_id, groups in steps_by_tab.items():
            for group in groups:
                for step in group:
                    all_steps.append(step)

        total = len(all_steps)

        try:
            # ── Launch browser ──────────────────────────────────────────────
            logger.info(f"[PLAY:{play_id}] launching browser {vp_width}×{vp_height}")
            browser, context, page = await self._browser_service.launch_browser(
                viewport_width=vp_width, viewport_height=vp_height, headless=True
            )

            # Viewport is already set at context creation — no set_viewport_size needed

            session.browser         = browser
            session.browser_context = context
            session.page            = page

            # Create per-session CaptureManager then attach DomWatcher to it
            cap_mgr = CaptureManager(self._screenshot_service, play_id, client_id)
            session.capture_manager = cap_mgr
            watcher = DomWatcher(cap_mgr)
            await watcher.attach(page, play_id, client_id)
            session.dom_watcher = watcher

            # ── Execute steps ───────────────────────────────────────────────
            failed_steps: list[dict] = []   # accumulate per-step failures

            for idx, step in enumerate(all_steps):
                step_id   = step.get("id", idx + 1)
                step_type = step.get("type", "UNKNOWN")
                should_run = step.get("shouldRun", True)
                pause      = step.get("pause", False)
                wait_ms    = step.get("waitAfterMs") or 0

                # Skip check
                if not should_run:
                    logger.info(f"[PLAY:{play_id}] step {step_id} ({step_type}) SKIPPED")
                    await self._send(play_id, client_id, PLAY_STEP_SKIPPED, {
                        "stepId": step_id, "index": idx, "total": total,
                    })
                    continue

                # Announce step start
                await self._send(play_id, client_id, PLAY_STEP_START, {
                    "stepId": step_id, "index": idx, "total": total, "type": step_type,
                })
                logger.info(f"[PLAY:{play_id}] step {idx+1}/{total} — {step_type}")

                # Execute
                step_failed = False
                try:
                    await self._execute_step(step, page)
                except asyncio.CancelledError:
                    raise  # propagate stop signal
                except Exception as step_err:
                    step_failed = True
                    err_msg = str(step_err)
                    logger.warning(f"[PLAY:{play_id}] step {step_id} ({step_type}) FAILED: {err_msg}")
                    failed_steps.append({"stepId": step_id, "type": step_type, "error": err_msg})
                    await self._send(play_id, client_id, PLAY_STEP_ERROR, {
                        "stepId": step_id, "index": idx, "type": step_type,
                        "error": err_msg,
                    })
                    # Capture failure state so frontend shows what went wrong
                    try:
                        await cap_mgr.request(page, CaptureReason.ERROR)
                    except Exception:
                        pass
                    break  # stop — do not proceed to remaining steps

                if not step_failed:
                    await self._settle_page(
                        page, play_id, step_id, step_type,
                        key_text=step.get("text", ""),
                        step_url=step.get("url"),
                        page_url=step.get("pageUrl"),
                    )

                # Opt 1: waitAfterMs removed — CaptureManager's FIXED_DELAY owns settle timing.
                # Opt 2: SCROLL/KEY use NONE settle (instant capture, no 300ms delay).
                # Opt 3: NAVIGATE skips STEP_DONE — DomWatcher streams the initial page frames.
                if not step_failed and step_type != "NAVIGATE":
                    _settle = SettleStrategy.NONE if step_type in ("SCROLL", "KEY") else None
                    try:
                        await cap_mgr.request(page, CaptureReason.STEP_DONE, settle=_settle)
                    except Exception as ss_err:
                        logger.warning(f"[PLAY:{play_id}] screenshot after step {step_id} failed (continuing): {ss_err}")

                # Pause check — block until PLAY_RESUME received
                if pause:
                    logger.info(f"[PLAY:{play_id}] PAUSED at step {step_id}")
                    session.status = PlayStatus.PAUSED
                    session.pause_event.clear()
                    await self._send(play_id, client_id, PLAY_PAUSED, {
                        "stepId": step_id, "index": idx,
                    })
                    await session.pause_event.wait()
                    session.status = PlayStatus.RUNNING
                    logger.info(f"[PLAY:{play_id}] RESUMED at step {step_id}")

            # ── Done ────────────────────────────────────────────────────────
            failed_count = len(failed_steps)
            session.status = PlayStatus.DONE
            logger.info(f"[PLAY:{play_id}] DONE — {total} steps, {failed_count} failed")
            await self._send(play_id, client_id, PLAY_DONE, {
                "stepCount": total,
                "failedCount": failed_count,
                "failedSteps": failed_steps,
                "message": "Playback complete" if failed_count == 0 else f"Playback done with {failed_count} step error(s)",
            })

        except asyncio.CancelledError:
            session.status = PlayStatus.STOPPED
            logger.info(f"[PLAY:{play_id}] task cancelled (STOP received)")

        except Exception as e:
            session.status = PlayStatus.ERROR
            logger.error(f"[PLAY:{play_id}] ERROR: {e}", exc_info=True)
            await self._send(play_id, client_id, PLAY_ERROR, {
                "error": str(e),
            })

        finally:
            # Always detach watcher and close browser
            if session.dom_watcher:
                try:
                    await session.dom_watcher.detach()
                except Exception:
                    pass
                session.dom_watcher = None

            if session.browser:
                try:
                    await session.browser.close()
                    logger.info(f"[PLAY:{play_id}] browser closed")
                except Exception:
                    pass
                session.browser = None
                session.page    = None

    # ─── Step dispatcher ───────────────────────────────────────────────────
    # ─── Step dispatcher (dispatch table) ────────────────────────────────
    async def _execute_step(self, step: dict, page) -> None:
        step_type = step.get("type")
        handler = self._STEP_HANDLERS.get(step_type)
        if handler:
            await handler(step, page)
        else:
            logger.warning(f"[PLAY] unknown step type: {step_type}")

    # ─── Individual step handlers ─────────────────────────────────────────
    async def _step_navigate(self, step: dict, page) -> None:
        url = step.get("url") or step.get("pageUrl")
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

    async def _step_click(self, step: dict, page) -> None:
        selector = step.get("selector")
        pw_selector = self._resolve_pw_selector(selector)
        coords = step.get("coords")
        button = step.get("button", "left") or "left"

        if pw_selector:
            occurrence_index = self._get_occurrence_index(selector)
            # Wait for the base selector to appear in the DOM.
            # SPAs may take several seconds to render after a preceding click.
            try:
                await page.wait_for_selector(pw_selector, timeout=3000)
            except Exception:
                pass

            matches = await page.query_selector_all(pw_selector)
            match_count = len(matches)

            if match_count == 0:
                if coords and await self._can_fallback_on_zero_match(step, page):
                    logger.warning(
                        f"[PLAY] selector '{pw_selector}' matched 0 elements, "
                        f"but targetMeta matched at coords ({coords['x']},{coords['y']}) — "
                        f"falling back to coords"
                    )
                    await self._browser_service.perform_click(
                        page, int(coords["x"]), int(coords["y"]), button
                    )
                    return
                raise Exception(
                    f"CLICK target '{pw_selector}' matched 0 elements "
                    f"(occurrence_index={occurrence_index}, url={page.url[:80]})."
                )

            if occurrence_index < match_count:
                await matches[occurrence_index].click(button=button)
                return

            # Base selector still matched, but the recorded occurrence is no longer present.
            if coords:
                logger.warning(
                    f"[PLAY] selector '{pw_selector}' matched {match_count} elements, "
                    f"but occurrence_index={occurrence_index} is out of range — "
                    f"falling back to coords ({coords['x']},{coords['y']})"
                )
                await self._browser_service.perform_click(
                    page, int(coords["x"]), int(coords["y"]), button
                )
                return

            raise Exception(
                f"CLICK target '{pw_selector}' matched {match_count} elements, "
                f"but occurrence_index={occurrence_index} is out of range "
                f"(url={page.url[:80]})."
            )
        elif coords:
            # No selector recorded — coords-only click (rare: canvas, dynamic elements).
            await self._browser_service.perform_click(
                page, int(coords["x"]), int(coords["y"]), button
            )

    async def _step_type(self, step: dict, page) -> None:
        selector = step.get("selector")
        text     = step.get("text") or ""
        if selector:
            pw_selector = self._resolve_pw_selector(selector)
            if pw_selector:
                # Wait up to 5s for the element before typing.
                try:
                    match = await page.wait_for_selector(pw_selector, timeout=5000)
                except Exception:
                    match = None
                if match is None:
                    raise Exception(
                        f"Expected element '{pw_selector}' not found on page "
                        f"(url={page.url[:80]}). Application may be in an unexpected state."
                    )
            await self._browser_service.perform_type(page, selector, text)
        else:
            await page.keyboard.type(text)

    async def _step_scroll(self, step: dict, page) -> None:
        coords = step.get("coords") or {}
        await self._browser_service.perform_scroll(
            page,
            int(coords.get("x", 0)),
            int(coords.get("y", 0)),
            float(step.get("deltaX") or 0),
            float(step.get("deltaY") or 0),
        )

    async def _step_key(self, step: dict, page) -> None:
        await self._browser_service.perform_key(page, step.get("text", "Enter"))

    # ─── Selector resolver — maps recorded strategy/value to Playwright selector ───
    def _resolve_pw_selector(self, recorded_selector: dict | None) -> str | None:
        if not recorded_selector:
            return None
        strategy = recorded_selector.get("strategy")
        value    = recorded_selector.get("value")
        if not strategy or not value:
            return None
        if strategy == "id":
            return f"#{value}"
        if strategy == "css":
            return value
        if strategy == "xpath":
            return f"xpath={value}"
        return None

    def _get_occurrence_index(self, recorded_selector: dict | None) -> int:
        if not recorded_selector:
            return 0
        return int(recorded_selector.get("occurrence_index") or 0)

    async def _can_fallback_on_zero_match(self, step: dict, page) -> bool:
        coords = step.get("coords") or {}
        target_meta = step.get("targetMeta") or {}
        if not coords or not target_meta:
            return False

        x = coords.get("x")
        y = coords.get("y")
        if x is None or y is None:
            return False

        live_info = await build_selector(page, int(x), int(y))
        if not live_info:
            return False

        live_meta = live_info.get("target_meta") or {}
        return self._target_meta_matches(target_meta, live_meta)

    def _target_meta_matches(self, recorded: dict[str, Any], live: dict[str, Any]) -> bool:
        def _norm(value: Any) -> str:
            if value is None:
                return ""
            return " ".join(str(value).strip().lower().split())

        strong_keys = {
            "id": 5,
            "dataTestId": 5,
            "dataId": 4,
            "dataCy": 4,
            "dataQa": 4,
            "name": 4,
            "ariaLabel": 4,
        }
        medium_keys = {
            "role": 3,
            "title": 3,
            "normalizedText": 3,
            "text": 2,
            "tag": 1,
        }

        compared = 0
        matched = 0

        for key, weight in {**strong_keys, **medium_keys}.items():
            rv = _norm(recorded.get(key))
            lv = _norm(live.get(key))
            if not rv or not lv:
                continue

            compared += weight
            if rv == lv:
                matched += weight
            elif key in strong_keys:
                return False

        if compared == 0:
            return False

        # Require enough overlapping confidence to allow coordinate fallback.
        return matched >= 4 and (matched / compared) >= 0.6

    # ─── Page settle — detect navigation only; CaptureManager owns all timing ──
    async def _settle_page(
        self,
        page,
        play_id: str,
        step_id: int,
        step_type: str,
        key_text: str = "",
        step_url: str | None = None,
        page_url: str | None = None,
    ) -> None:
        """
        Only run the URL-change poll when the recording proves navigation happened.
        A step navigated if: step_url is non-null AND differs from pageUrl.
        For SPA clicks (dropdown, tab, button) step_url == pageUrl → skip immediately.
        CaptureManager's FIXED_DELAY(300ms) owns settle for all non-navigating steps.
        """
        is_navigating_type = step_type == "CLICK" or (step_type == "KEY" and key_text == "Enter")
        recorded_navigation = step_url is not None and step_url != page_url
        if not is_navigating_type or not recorded_navigation:
            return

        url_before = page.url
        try:
            await page.wait_for_function(
                f"() => location.href !== {json.dumps(url_before)}",
                timeout=500,
            )
            logger.info(f"[PLAY:{play_id}] step {step_id} navigated \u2192 {page.url[:80]}")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
        except Exception:
            pass  # no navigation detected — CaptureManager's FIXED_DELAY owns settle

    # ─── Helper: send WS event to client ──────────────────────────────────
    async def _send(self, play_id: str, client_id: str, event_type: str, data: dict) -> None:
        try:
            await self._connection_manager.send_to_client(play_id, client_id, {
                "event_type": event_type,
                "data": data,
            })
        except Exception as e:
            logger.warning(f"[PLAY:{play_id}] send failed ({event_type}): {e}")
