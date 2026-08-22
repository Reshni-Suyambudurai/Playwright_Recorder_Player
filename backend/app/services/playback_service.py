"""
PlaybackService — executes a recorded JSON step-by-step in a Playwright browser,
streaming FRAME events and playback lifecycle events to the frontend.

Reuses: BrowserService, ScreenshotService, DomWatcher from the recording stack.
"""
import asyncio
import difflib
import json
import logging
import re
from typing import Any

from app.models.playback import PlaySession, PlayStatus
from app.services.browser_service import BrowserService
from app.services.screenshot_service import ScreenshotService
from app.services.dom_watcher import DomWatcher
from app.services.capture_manager import CaptureManager, CaptureReason, SettleStrategy
from app.services.assertion_service import AssertionService
from app.services.snapshot_service import SnapshotService
from app.utils.selector_builder import build_selector
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger("playwright_recorder.services.playback")

CLICK_RETRY_ATTEMPTS = 3
CLICK_RETRY_DELAY_SECONDS = 0.2
FALLBACK_STABILIZE_DELAY_SECONDS = 0.35

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
        # Stateless — one shared instance reused across every ASSERTION step in a playback run
        self._assertion_service = AssertionService()
        self._snapshot_service  = SnapshotService()
        # Dispatch table: step type → handler method
        # Add new step types here without touching _execute_step
        self._STEP_HANDLERS = {
            "NAVIGATE":  self._step_navigate,
            "CLICK":     self._step_click,
            "TYPE":      self._step_type,
            "SCROLL":    self._step_scroll,
            "KEY":       self._step_key,
            "ASSERTION": self._step_assertion,
        }
        self._active_play_id: str | None = None

    def apply_runtime_step_patches(self, session: PlaySession, patches: list[dict[str, Any]]) -> dict[str, Any]:
        received_count = len(patches)
        applied_count = 0
        unresolved_step_ids: list[int] = []

        steps_by_id: dict[int, dict[str, Any]] = {}
        steps_root = session.recording_json.get("steps", {})
        for groups in steps_root.values():
            for group in groups:
                for step in group:
                    step_id = step.get("id")
                    if isinstance(step_id, int):
                        steps_by_id[step_id] = step

        for patch in patches:
            step_id = patch.get("stepId")
            if not isinstance(step_id, int):
                continue

            step = steps_by_id.get(step_id)
            if not step:
                unresolved_step_ids.append(step_id)
                continue

            changed = False
            if "shouldRun" in patch and patch.get("shouldRun") is not None:
                next_should_run = bool(patch["shouldRun"])
                if step.get("shouldRun", True) != next_should_run:
                    step["shouldRun"] = next_should_run
                    changed = True

            if "pause" in patch and patch.get("pause") is not None:
                next_pause = bool(patch["pause"])
                if step.get("pause", False) != next_pause:
                    step["pause"] = next_pause
                    changed = True

            if changed:
                applied_count += 1

        message = "Runtime step changes applied"
        if unresolved_step_ids:
            message = "Runtime step changes applied partially"

        return {
            "receivedCount": received_count,
            "appliedCount": applied_count,
            "unresolvedStepIds": unresolved_step_ids,
            "message": message,
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
        self._active_play_id = play_id
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

                    # Reuse normal pause flow for manual intervention on failures.
                    session.status = PlayStatus.PAUSED
                    session.pause_event.clear()
                    await self._send(play_id, client_id, PLAY_PAUSED, {
                        "stepId": step_id,
                        "index": idx,
                        "reason": "error",
                        "error": err_msg,
                    })
                    await session.pause_event.wait()
                    session.status = PlayStatus.RUNNING
                    continue

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
            session.mark_finished()
            logger.info(f"[PLAY:{play_id}] DONE — {total} steps, {failed_count} failed")
            await self._send(play_id, client_id, PLAY_DONE, {
                "stepCount": total,
                "failedCount": failed_count,
                "failedSteps": failed_steps,
                "message": "Playback complete" if failed_count == 0 else f"Playback done with {failed_count} step error(s)",
            })

        except asyncio.CancelledError:
            session.status = PlayStatus.STOPPED
            session.mark_finished()
            logger.info(f"[PLAY:{play_id}] task cancelled (STOP received)")

        except Exception as e:
            session.status = PlayStatus.ERROR
            session.mark_finished()
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
            self._active_play_id = None

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
            click_error: Exception | None = None
            wait_timed_out = False
            wait_error = ""
            matches: list[Any] = []
            match_count = 0

            # Retry lookup/click to allow SPA/React DOM settle before declaring mismatch.
            for attempt in range(CLICK_RETRY_ATTEMPTS):
                try:
                    await self._wait_for_selector_visible(page, pw_selector, timeout_ms=3000)
                except Exception as exc:
                    wait_timed_out = True
                    wait_error = str(exc)

                matches = await page.query_selector_all(pw_selector)
                match_count = len(matches)

                if occurrence_index < match_count:
                    try:
                        await matches[occurrence_index].click(button=button)
                        return
                    except Exception as exc:
                        click_error = exc

                if attempt < CLICK_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(CLICK_RETRY_DELAY_SECONDS)

            if match_count == 0:
                # Do not fallback immediately after timeout; let UI settle first.
                await self._wait_for_ui_stabilization(page)

                recovered = await self._try_dropdown_value_recovery(step, page)
                if recovered:
                    return

                fallback_allowed = False
                live_meta: dict[str, Any] | None = None
                fallback_reason = ""
                if coords:
                    fallback_allowed, live_meta, fallback_reason = await self._can_fallback_on_zero_match(step, page)

                if coords and fallback_allowed:
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
                    f"(occurrence_index={occurrence_index}, url={page.url[:80]}, "
                    f"wait_timed_out={wait_timed_out})."
                )

            # Base selector still matched, but the recorded occurrence is no longer present.
            if coords:
                await self._wait_for_ui_stabilization(page)
                logger.warning(
                    f"[PLAY] selector '{pw_selector}' matched {match_count} elements, "
                    f"but occurrence_index={occurrence_index} is out of range — "
                    f"falling back to coords ({coords['x']},{coords['y']})"
                )
                await self._browser_service.perform_click(
                    page, int(coords["x"]), int(coords["y"]), button
                )
                return

            if click_error:
                raise Exception(
                    f"CLICK target '{pw_selector}' found but not actionable "
                    f"(occurrence_index={occurrence_index}, error={click_error})."
                )

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
                    match = await self._wait_for_selector_visible(page, pw_selector, timeout_ms=5000)
                except Exception as exc:
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

    async def _step_assertion(self, step: dict, page) -> None:
        """
        Re-run a recorded assertion live and compare it against what was captured at record
        time. Reuses AssertionService/SnapshotService — the same extractors used during
        recording — so replayed and recorded values are always produced by identical logic.
        Raises on mismatch, which flows through the standard step-failure path (PLAY_STEP_ERROR
        + pause-for-review), same as a failed CLICK or TYPE.
        """
        assertion_type = step.get("assertionType") or step.get("assertion_type") or ""
        expected = step.get("discoveredData") or {}

        if assertion_type == "snapshot":
            region = expected.get("region") or {}
            actual = await self._snapshot_service.capture_aria_snapshot(
                page,
                int(region.get("x", 0)), int(region.get("y", 0)),
                int(region.get("width", 0)), int(region.get("height", 0)),
            )
            if actual.get("error"):
                raise Exception(f"ASSERTION (snapshot) could not be re-captured: {actual['error']}")
        else:
            element = await self._resolve_assertion_element(step, page)
            if element is not None:
                # Read data straight from the resolved element — no pixel re-guessing, so
                # this can't land on the wrong element the way coordinate hit-testing could.
                actual = await self._assertion_service.discover_from_element(element, assertion_type)
            else:
                # Selector couldn't be resolved at all; coords-only hit-test is the last resort.
                coords = step.get("coords") or {}
                if not coords:
                    raise Exception("ASSERTION target not found: no selector match and no recorded coords")
                actual = await self._assertion_service.discover_by_mode(
                    page, int(coords.get("x", 0)), int(coords.get("y", 0)), assertion_type
                )

        passed, reason = self._compare_assertion(assertion_type, expected, actual)
        if not passed:
            raise Exception(f"ASSERTION ({assertion_type}) failed: {reason}")

    async def _resolve_assertion_element(self, step: dict, page):
        """
        Resolve the live element to inspect for a visibility/text/value assertion, via the
        recorded selector (mirrors _step_click's selector-first strategy). Returns None if the
        selector can't be found, so the caller can fall back to the recorded coords instead.
        """
        selector = step.get("selector")
        pw_selector = self._resolve_pw_selector(selector)
        if not pw_selector:
            return None

        try:
            await self._wait_for_selector_visible(page, pw_selector, timeout_ms=3000)
            matches = await page.query_selector_all(pw_selector)
            occurrence_index = self._get_occurrence_index(selector)
            if occurrence_index < len(matches):
                return matches[occurrence_index]
        except Exception:
            pass  # fall through to coords fallback

        return None

    def _compare_assertion(self, assertion_type: str, expected: dict, actual: dict) -> tuple[bool, str]:
        """Compare recorded vs. freshly-discovered assertion data. Returns (passed, reason)."""
        if assertion_type == "visibility":
            exp_visible, act_visible = bool(expected.get("visible")), bool(actual.get("visible"))
            if exp_visible != act_visible:
                return False, f"expected visible={exp_visible}, got visible={act_visible}"
            return True, ""

        if assertion_type in ("text", "value"):
            exp_val, act_val = expected.get(assertion_type), actual.get(assertion_type)
            if self._normalize_text(exp_val) != self._normalize_text(act_val):
                return False, f"expected {assertion_type}={exp_val!r}, got {act_val!r}"
            return True, ""

        if assertion_type == "snapshot":
            # Exact word-by-word match — playback never exits on a mismatch (it pauses for
            # review, same as any other step failure), so there's no need to tolerate drift;
            # any difference is worth surfacing to the user.
            exp_words = str(expected.get("ariaSnapshot") or "").split()
            act_words = str(actual.get("ariaSnapshot") or "").split()
            if exp_words != act_words:
                diff_excerpt = self._snapshot_diff_excerpt(exp_words, act_words)
                return False, f"snapshot content changed:\n{diff_excerpt}"
            return True, ""

        return False, f"unknown assertion type: {assertion_type!r}"

    def _snapshot_diff_excerpt(self, expected_words: list[str], actual_words: list[str], max_diffs: int = 6) -> str:
        """
        Word-by-word diff excerpt of exactly what changed, for the failure message sent to
        the frontend. Reports each mismatched run as "word N: expected 'X', got 'Y'".
        """
        matcher = difflib.SequenceMatcher(None, expected_words, actual_words)
        mismatches = [
            (i1, expected_words[i1:i2], actual_words[j1:j2])
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        ]
        if not mismatches:
            return "(content differs but no word-level diff available)"

        lines = [
            f"word {i1 + 1}: expected {' '.join(exp) or '(nothing)'!r}, got {' '.join(act) or '(nothing)'!r}"
            for i1, exp, act in mismatches[:max_diffs]
        ]
        if len(mismatches) > max_diffs:
            lines.append(f"... ({len(mismatches) - max_diffs} more mismatch(es))")
        return "\n".join(lines)

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

    async def _can_fallback_on_zero_match(self, step: dict, page) -> tuple[bool, dict[str, Any] | None, str]:
        coords = step.get("coords") or {}
        target_meta = step.get("targetMeta") or {}
        if not coords or not target_meta:
            return False, None, "missing_coords_or_target_meta"

        x = coords.get("x")
        y = coords.get("y")
        if x is None or y is None:
            return False, None, "missing_coordinate_values"

        live_info = await build_selector(page, int(x), int(y))
        if not live_info:
            return False, None, "no_live_selector_info"

        live_meta = live_info.get("target_meta") or {}
        matched = self._target_meta_matches(target_meta, live_meta)
        return matched, live_meta, "target_meta_match" if matched else "target_meta_mismatch"

    async def _wait_for_selector_visible(self, page, pw_selector: str, timeout_ms: int):
        try:
            return await page.wait_for_selector(pw_selector, state="visible", timeout=timeout_ms)
        except TypeError:
            # Test doubles and older wrappers may not support the 'state' argument.
            return await page.wait_for_selector(pw_selector, timeout=timeout_ms)

    async def _wait_for_ui_stabilization(self, page) -> None:
        await asyncio.sleep(FALLBACK_STABILIZE_DELAY_SECONDS)
        try:
            await page.evaluate(
                """() => new Promise((resolve) => {
                    requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
                })"""
            )
        except Exception:
            pass

    async def _try_dropdown_value_recovery(self, step: dict[str, Any], page) -> bool:
        if not self._is_dropdown_value_step(step):
            return False

        target_meta = step.get("targetMeta") or {}
        recorded_value = (
            target_meta.get("normalizedText")
            or target_meta.get("text")
            or ""
        )
        recorded_value = str(recorded_value).strip()
        if not recorded_value:
            return False

        recorded_norm = self._normalize_text(recorded_value)
        xpath_literal = self._to_xpath_literal(recorded_value)

        candidate_selectors = [
            f"xpath=//*[@role='option' and normalize-space(.)={xpath_literal}]",
            f"xpath=//*[contains(@class,'zdropdownlist__text') and normalize-space(.)={xpath_literal}]",
            f"xpath=//span[normalize-space(.)={xpath_literal}]",
            f"xpath=//li[normalize-space(.)={xpath_literal}]",
            f"xpath=//div[normalize-space(.)={xpath_literal}]",
        ]

        for candidate_selector in candidate_selectors:
            elements = await page.query_selector_all(candidate_selector)
            if not elements:
                continue

            for element in elements:
                text = await self._extract_element_text(element)
                if self._normalize_text(text) != recorded_norm:
                    continue
                try:
                    await element.click(button=step.get("button", "left") or "left")
                    return True
                except Exception:
                    continue

        return False

    async def _extract_element_text(self, element) -> str:
        for attr in ("inner_text", "text_content"):
            fn = getattr(element, attr, None)
            if callable(fn):
                try:
                    value = await fn()
                    if value:
                        return str(value)
                except Exception:
                    continue
        return ""

    def _is_dropdown_value_step(self, step: dict[str, Any]) -> bool:
        target_meta = step.get("targetMeta") or {}
        role = str(target_meta.get("role") or "").strip().lower()
        class_hints = [str(c).lower() for c in (target_meta.get("classHints") or [])]
        hint_blob = " ".join(class_hints)
        has_value = bool((target_meta.get("text") or target_meta.get("normalizedText") or "").strip())

        if not has_value:
            return False

        if role in {"listbox", "combobox", "option"}:
            return True

        return any(token in hint_blob for token in ("dropdown", "listbox", "select", "zdropdownlist__text"))

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value).strip().lower())

    def _to_xpath_literal(self, value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        encoded_parts = []
        for index, part in enumerate(parts):
            if part:
                encoded_parts.append(f"'{part}'")
            if index < len(parts) - 1:
                encoded_parts.append('"\'"')
        return f"concat({', '.join(encoded_parts)})"

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
