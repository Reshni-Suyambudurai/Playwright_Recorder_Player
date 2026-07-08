"""
PlaybackService — executes a recorded JSON step-by-step in a Playwright browser,
streaming FRAME events and playback lifecycle events to the frontend.

Reuses: BrowserService, ScreenshotService, DomWatcher from the recording stack.
"""
import asyncio
import json
import logging

from app.models.playback import PlaySession, PlayStatus
from app.services.browser_service import BrowserService
from app.services.screenshot_service import ScreenshotService
from app.services.dom_watcher import DomWatcher
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

            # Attach DomWatcher (same as recording — sends FRAME on DOM changes)
            watcher = DomWatcher(self._screenshot_service)
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
                watcher.suppress_external(True)
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
                        await self._screenshot_service.capture_and_send(page, play_id, client_id, caller="ERROR")
                    except Exception:
                        pass
                    break  # stop — do not proceed to remaining steps
                finally:
                    watcher.suppress_external(False)

                # Wait for page to settle after each step.
                # Poll up to 2s for a URL change (fast navigations).
                # If URL changed, wait for the new page to fully load (up to 8s networkidle).
                # If no navigation in 2s, just ensure the current page is idle (up to 2s).
                if not step_failed:
                    url_at_action = page.url
                    await asyncio.sleep(0.3)   # let any navigation start

                    try:
                        await page.wait_for_function(
                            f"() => location.href !== {json.dumps(url_at_action)}",
                            timeout=2000,
                        )
                        # URL changed — wait for new page to fully load
                        logger.info(f"[PLAY:{play_id}] step {step_id} navigated → {page.url[:80]}")
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except Exception:
                            pass
                        try:
                            await page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            pass
                    except Exception:
                        # No navigation — just settle current page
                        try:
                            await page.wait_for_load_state("networkidle", timeout=2000)
                        except Exception:
                            pass

                # waitAfterMs settle delay (100–300ms hardcoded by recorder)
                if wait_ms > 0 and not step_failed:
                    await asyncio.sleep(wait_ms / 1000)

                # Take screenshot after each step (even on error, to show current state)
                try:
                    await self._screenshot_service.capture_and_send(page, play_id, client_id, caller=step_type)
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
    async def _execute_step(self, step: dict, page) -> None:
        step_type = step.get("type")

        if step_type == "NAVIGATE":
            url = step.get("url") or step.get("pageUrl")
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        elif step_type == "CLICK":
            coords = step.get("coords")
            if coords:
                button = step.get("button", "left") or "left"

                # ── Selector check ────────────────────────────────────────────
                # If the recorded selector exists on the current page,
                # click it directly (more accurate than coords).
                # If not found, fall back to coords — no error raised.
                recorded_selector = step.get("selector")
                selector_clicked = False
                if recorded_selector:
                    strategy = recorded_selector.get("strategy")
                    value    = recorded_selector.get("value")
                    if strategy and value:
                        if strategy == "id":
                            pw_selector = f"#{value}"
                        elif strategy == "css":
                            pw_selector = value
                        elif strategy == "xpath":
                            pw_selector = f"xpath={value}"
                        else:
                            pw_selector = None

                        if pw_selector:
                            try:
                                match = await page.query_selector(pw_selector)
                                if match is None:
                                    logger.warning(
                                        f"[PLAY] CLICK selector '{pw_selector}' not found — "
                                        f"falling back to coords ({coords['x']},{coords['y']})"
                                    )
                                else:
                                    await match.click(button=button)
                                    selector_clicked = True
                            except Exception as sel_err:
                                logger.warning(
                                    f"[PLAY] CLICK selector '{pw_selector}' error ({sel_err}) — "
                                    f"falling back to coords ({coords['x']},{coords['y']})"
                                )

                if not selector_clicked:
                    # Coords fallback — report clearly if it also fails
                    try:
                        await self._browser_service.perform_click(
                            page, int(coords["x"]), int(coords["y"]), button
                        )
                    except Exception as coords_err:
                        raise Exception(
                            f"CLICK failed: selector not found AND coords ({coords['x']},{coords['y']}) "
                            f"also failed ({coords_err})"
                        )

        elif step_type == "TYPE":
            selector = step.get("selector")
            text     = step.get("text") or ""
            if selector:
                # Pre-check: verify the target element exists before typing
                strategy = selector.get("strategy")
                value    = selector.get("value")
                if strategy == "id":
                    css_query = f"#{value}"
                elif strategy == "css":
                    css_query = value
                elif strategy == "xpath":
                    css_query = f"xpath={value}"
                else:
                    css_query = None

                if css_query:
                    match = await page.query_selector(css_query)
                    if match is None:
                        raise Exception(
                            f"Expected element '{css_query}' not found on page "
                            f"(url={page.url[:80]}). "
                            f"Application may be in an unexpected state."
                        )

                await self._browser_service.perform_type(page, selector, text)
                # If this is a password field, press Enter to submit the form.
                # Many SSO flows (e.g. Microsoft) require Enter after the password
                # because the user pressed Enter during recording instead of clicking
                # the Sign In button, so no explicit CLICK step was recorded.
                if step.get("isPassword"):
                    logger.info("[PLAY] isPassword step — pressing Enter to submit")
                    await page.keyboard.press("Enter")
            else:
                await page.keyboard.type(text)

        elif step_type == "SCROLL":
            coords = step.get("coords", {}) or {}
            await self._browser_service.perform_scroll(
                page,
                int(coords.get("x", 0)),
                int(coords.get("y", 0)),
                float(step.get("deltaX") or 0),
                float(step.get("deltaY") or 0),
            )

        elif step_type == "KEY":
            key = step.get("text", "Enter")
            await self._browser_service.perform_key(page, key)

        else:
            logger.warning(f"[PLAY] unknown step type: {step_type}")

    # ─── Helper: send WS event to client ──────────────────────────────────
    async def _send(self, play_id: str, client_id: str, event_type: str, data: dict) -> None:
        try:
            await self._connection_manager.send_to_client(play_id, client_id, {
                "event_type": event_type,
                "data": data,
            })
        except Exception as e:
            logger.warning(f"[PLAY:{play_id}] send failed ({event_type}): {e}")
