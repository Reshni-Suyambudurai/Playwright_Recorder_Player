"""Playback service for replaying recorded actions with actual browser automation"""
import logging
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path(__file__).parent.parent / "JSON_Recordings"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


class PlaybackService:
    """Service for playback of recorded actions with actual browser automation"""

    @staticmethod
    def load_recording(recording_id: str) -> Optional[Dict]:
        """Load recording by ID"""
        try:
            if RECORDINGS_DIR.exists():
                for date_folder in RECORDINGS_DIR.glob("recordings_*"):
                    for recording_file in date_folder.glob("recording_*.json"):
                        with open(recording_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if data.get("meta", {}).get("id") == recording_id:
                                logger.info(f"[OK] Recording loaded: {recording_id}")
                                return data
            
            logger.warning(f"[WARN] Recording not found: {recording_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to load recording: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def play_recording(recording_id: str) -> Dict[str, Any]:
        """
        Playback a recording by launching actual browser and executing actions
        
        Args:
            recording_id: Recording ID to playback
            
        Returns:
            dict with playback results
        """
        browser = None
        page = None
        playwright = None
        
        try:
            # Load recording
            recording_data = PlaybackService.load_recording(recording_id)
            if not recording_data:
                return {
                    "status": "error",
                    "message": f"Recording {recording_id} not found",
                    "total_actions": 0,
                    "completed_actions": 0,
                    "failed_actions": 0,
                    "actions_log": [],
                    "screenshots": []
                }

            logger.info(f"[START] Starting playback of recording: {recording_id}")
            title = recording_data.get('meta', {}).get('title', 'Untitled')
            logger.info(f"[TITLE] Recording: {title}")

            # Get viewport from first action or use default
            viewport = {"width": 1280, "height": 720}
            steps = recording_data.get("steps", {}).get("tab-1", [])
            if steps and len(steps) > 0 and len(steps[0]) > 0:
                first_action = steps[0][0]
                action_viewport = first_action.get("viewport", {})
                if action_viewport:
                    viewport = {
                        "width": action_viewport.get("width", 1280),
                        "height": action_viewport.get("height", 720)
                    }
            
            logger.info(f"[VIEWPORT] Using viewport: {viewport['width']}x{viewport['height']}")

            # Launch browser in headless mode with proper viewport
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)

            # Extract all actions
            all_actions = []
            for action_group in steps:
                all_actions.extend(action_group)

            logger.info(f"[ACTIONS] Total actions to execute: {len(all_actions)}")

            # Track results
            results = {
                "status": "success",
                "recording_id": recording_id,
                "title": title,
                "viewport": viewport,
                "total_actions": len(all_actions),
                "completed_actions": 0,
                "failed_actions": 0,
                "actions_log": [],
                "screenshots": []
            }

            # Execute each action
            for idx, action_data in enumerate(all_actions, 1):
                try:
                    action_type = action_data.get('type', 'UNKNOWN')
                    logger.info(f"\n[ACTION {idx}] Executing: {action_type}")
                    
                    action_result = PlaybackService._execute_action_in_browser(
                        page, action_data, idx
                    )
                    results["actions_log"].append(action_result)
                    
                    # Take screenshot after action
                    if action_result["status"] == "success":
                        screenshot_name = f"playback_{recording_id.split('-')[0]}_{idx:02d}_{action_type}.png"
                        screenshot_path = SCREENSHOTS_DIR / screenshot_name
                        try:
                            page.screenshot(path=str(screenshot_path))
                            results["screenshots"].append(screenshot_name)
                            logger.info(f"[SCREENSHOT] Saved: {screenshot_name}")
                        except Exception as e:
                            logger.warning(f"[SCREENSHOT] Failed to save: {e}")
                    
                    if action_result["status"] == "success":
                        results["completed_actions"] += 1
                        logger.info(f"[OK] Action {idx}/{len(all_actions)}: {action_type} - SUCCESS")
                    else:
                        results["failed_actions"] += 1
                        logger.warning(f"[FAIL] Action {idx}/{len(all_actions)}: {action_type} - FAILED: {action_result['message']}")
                        
                except Exception as e:
                    logger.error(f"[ERROR] Action {idx} execution error: {str(e)}", exc_info=True)
                    action_type = action_data.get("type", "UNKNOWN")
                    results["actions_log"].append({
                        "id": idx,
                        "type": action_type,
                        "status": "error",
                        "message": str(e),
                        "label": action_data.get("label", "")
                    })
                    results["failed_actions"] += 1

            # Playback summary
            results["success_rate"] = (results["completed_actions"] / len(all_actions) * 100) if all_actions else 0
            results["overall_status"] = "success" if results["failed_actions"] == 0 else "partial"

            logger.info(f"\n{'='*60}")
            logger.info(f"[SUMMARY] Playback Complete:")
            logger.info(f"  Recording: {title}")
            logger.info(f"  Total Actions: {results['total_actions']}")
            logger.info(f"  Completed: {results['completed_actions']}")
            logger.info(f"  Failed: {results['failed_actions']}")
            logger.info(f"  Success Rate: {results['success_rate']:.1f}%")
            logger.info(f"  Screenshots: {len(results['screenshots'])}")
            logger.info(f"{'='*60}\n")

            return results

        except Exception as e:
            logger.error(f"[FATAL] Playback failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Playback error: {str(e)}",
                "total_actions": 0,
                "completed_actions": 0,
                "failed_actions": 0,
                "actions_log": [],
                "screenshots": []
            }
        
        finally:
            # Cleanup resources
            try:
                if page:
                    page.close()
                    logger.info("[CLEANUP] Page closed")
                if browser:
                    browser.close()
                    logger.info("[CLEANUP] Browser closed")
                if playwright:
                    playwright.stop()
                    logger.info("[CLEANUP] Playwright stopped")
            except Exception as e:
                logger.error(f"[CLEANUP ERROR] {str(e)}")

    @staticmethod
    def _execute_action_in_browser(page, action_data: Dict, action_index: int) -> Dict[str, Any]:
        """
        Execute a single action in the browser
        
        Args:
            page: Playwright page object
            action_data: Action data from recording
            action_index: Sequential action number
            
        Returns:
            Result dict with status and details
        """
        action_type = action_data.get("type", "UNKNOWN")
        
        try:
            if action_type == "NAVIGATE":
                return PlaybackService._execute_navigate(page, action_data, action_index)
            
            elif action_type == "CLICK":
                return PlaybackService._execute_click(page, action_data, action_index)
            
            elif action_type == "TYPE":
                return PlaybackService._execute_type(page, action_data, action_index)
            
            elif action_type == "SCROLL":
                return PlaybackService._execute_scroll(page, action_data, action_index)
            
            elif action_type == "WAIT":
                return PlaybackService._execute_wait(page, action_data, action_index)
            
            else:
                return {
                    "id": action_index,
                    "type": action_type,
                    "status": "skipped",
                    "message": f"Action type '{action_type}' not supported",
                    "label": action_data.get("label", "")
                }

        except Exception as e:
            logger.error(f"[ACTION ERROR] {action_index}: {str(e)}", exc_info=True)
            return {
                "id": action_index,
                "type": action_type,
                "status": "error",
                "message": str(e)[:200],
                "label": action_data.get("label", "")
            }

    @staticmethod
    def _execute_navigate(page, action_data: Dict, action_index: int) -> Dict:
        """Execute NAVIGATE action"""
        url = action_data.get("url")
        if not url:
            return {
                "id": action_index,
                "type": "NAVIGATE",
                "status": "error",
                "message": "No URL provided",
                "label": action_data.get("label", "")
            }

        try:
            wait_until = action_data.get("waitUntil", "domcontentloaded")
            logger.info(f"  [NAVIGATE] Going to: {url} (wait: {wait_until})")
            page.goto(url, wait_until=wait_until, timeout=30000)
            
            # Wait based on action spec
            wait_after = action_data.get("waitAfterMs", 100)
            if wait_after:
                time.sleep(wait_after / 1000.0)
            
            return {
                "id": action_index,
                "type": "NAVIGATE",
                "status": "success",
                "url": url,
                "message": f"Navigated to {url}",
                "label": action_data.get("label", "")
            }
        except Exception as e:
            logger.error(f"  [NAVIGATE ERROR] {str(e)}")
            return {
                "id": action_index,
                "type": "NAVIGATE",
                "status": "error",
                "url": url,
                "message": str(e)[:200],
                "label": action_data.get("label", "")
            }

    @staticmethod
    def _execute_click(page, action_data: Dict, action_index: int) -> Dict:
        """Execute CLICK action with selector first, fallback to coordinates"""
        selector_data = action_data.get("selector")
        coords = action_data.get("coords")
        tag = action_data.get("tag", "unknown")
        label = action_data.get("label", "")

        result = {
            "id": action_index,
            "type": "CLICK",
            "tag": tag,
            "label": label,
        }

        try:
            # Strategy 1: Try selector first (most reliable)
            if selector_data and selector_data.get("value"):
                selector_strategy = selector_data.get("strategy", "css")
                selector_value = selector_data.get("value")
                
                try:
                    logger.info(f"  [CLICK] Trying {selector_strategy} selector: {selector_value[:80]}")
                    page.click(selector_value, timeout=5000)
                    
                    result["status"] = "success"
                    result["method"] = "selector"
                    result["selector"] = selector_value[:100]
                    result["message"] = f"Clicked using {selector_strategy} selector"
                    
                except Exception as selector_error:
                    logger.warning(f"  [CLICK] Selector failed: {str(selector_error)[:100]}")
                    
                    # Strategy 2: Fallback to coordinates
                    if coords and "x" in coords and "y" in coords:
                        try:
                            x, y = int(coords.get("x")), int(coords.get("y"))
                            logger.info(f"  [CLICK] Fallback to coordinates: ({x}, {y})")
                            page.click("body", position={"x": x, "y": y})
                            
                            result["status"] = "success"
                            result["method"] = "coordinates"
                            result["coords"] = coords
                            result["message"] = f"Clicked at ({x}, {y}) after selector failed"
                            
                        except Exception as coord_error:
                            logger.error(f"  [CLICK] Coordinates also failed: {str(coord_error)}")
                            result["status"] = "error"
                            result["method"] = "both_failed"
                            result["message"] = f"Selector & Coords failed"
                    else:
                        result["status"] = "error"
                        result["method"] = "selector_only"
                        result["message"] = f"Selector failed, no coords"
            
            # If no selector, try coordinates
            elif coords and "x" in coords and "y" in coords:
                try:
                    x, y = int(coords.get("x")), int(coords.get("y"))
                    logger.info(f"  [CLICK] Coordinates: ({x}, {y})")
                    page.click("body", position={"x": x, "y": y})
                    
                    result["status"] = "success"
                    result["method"] = "coordinates"
                    result["coords"] = coords
                    result["message"] = f"Clicked at ({x}, {y})"
                    
                except Exception as e:
                    logger.error(f"  [CLICK] Coordinates failed: {str(e)}")
                    result["status"] = "error"
                    result["method"] = "coordinates_only"
                    result["message"] = str(e)[:100]
            else:
                result["status"] = "error"
                result["message"] = "No selector or coordinates"

            # Wait after click
            wait_after = action_data.get("waitAfterMs", 300)
            if wait_after and result["status"] == "success":
                time.sleep(wait_after / 1000.0)

            return result

        except Exception as e:
            logger.error(f"  [CLICK EXCEPTION] {str(e)}")
            result["status"] = "error"
            result["message"] = str(e)[:200]
            return result

    @staticmethod
    def _execute_type(page, action_data: Dict, action_index: int) -> Dict:
        """Execute TYPE action"""
        selector_data = action_data.get("selector")
        coords = action_data.get("coords")
        text = action_data.get("text", "")
        label = action_data.get("label", "")

        result = {
            "id": action_index,
            "type": "TYPE",
            "label": label,
            "text": text[:20] + "..." if len(text) > 20 else text
        }

        try:
            # Focus element first (selector priority)
            if selector_data and selector_data.get("value"):
                selector_value = selector_data.get("value")
                try:
                    logger.info(f"  [TYPE] Into selector: {selector_value[:80]}")
                    page.click(selector_value)
                    page.fill(selector_value, text)
                    result["status"] = "success"
                    result["method"] = "selector"
                    result["selector"] = selector_value[:100]
                except Exception as e:
                    logger.warning(f"  [TYPE] Selector failed: {str(e)[:100]}")
                    # Fallback to coordinates if available
                    if coords and "x" in coords and "y" in coords:
                        x, y = int(coords.get("x")), int(coords.get("y"))
                        logger.info(f"  [TYPE] Fallback to coordinates: ({x}, {y})")
                        page.click("body", position={"x": x, "y": y})
                        page.type("input, textarea, [contenteditable]", text)
                        result["status"] = "success"
                        result["method"] = "coordinates"
                        result["coords"] = coords
                    else:
                        raise

            # Fallback to coordinates
            elif coords and "x" in coords and "y" in coords:
                x, y = int(coords.get("x")), int(coords.get("y"))
                logger.info(f"  [TYPE] At coordinates: ({x}, {y})")
                page.click("body", position={"x": x, "y": y})
                page.type("input, textarea, [contenteditable]", text)
                result["status"] = "success"
                result["method"] = "coordinates"
                result["coords"] = coords
            else:
                result["status"] = "error"
                result["message"] = "No selector or coordinates"
                return result

            # Handle press Enter
            if action_data.get("pressEnter"):
                page.press("input, textarea, [contenteditable]", "Enter")
                result["pressed_enter"] = True

            result["message"] = f"Typed text using {result.get('method', 'unknown')}"

            # Wait after type
            wait_after = action_data.get("waitAfterMs", 100)
            if wait_after:
                time.sleep(wait_after / 1000.0)

            return result

        except Exception as e:
            logger.error(f"  [TYPE ERROR] {str(e)}")
            result["status"] = "error"
            result["message"] = str(e)[:200]
            return result

    @staticmethod
    def _execute_scroll(page, action_data: Dict, action_index: int) -> Dict:
        """Execute SCROLL action"""
        delta_y = action_data.get("deltaY", 0)
        label = action_data.get("label", "")

        result = {
            "id": action_index,
            "type": "SCROLL",
            "deltaY": delta_y,
            "label": label
        }

        try:
            logger.info(f"  [SCROLL] By {delta_y}px")
            page.evaluate(f"window.scrollBy(0, {delta_y})")
            
            result["status"] = "success"
            result["message"] = f"Scrolled {delta_y}px"

            # Wait after scroll
            wait_after = action_data.get("waitAfterMs", 100)
            if wait_after:
                time.sleep(wait_after / 1000.0)

            return result

        except Exception as e:
            logger.error(f"  [SCROLL ERROR] {str(e)}")
            result["status"] = "error"
            result["message"] = str(e)[:200]
            return result

    @staticmethod
    def _execute_wait(page, action_data: Dict, action_index: int) -> Dict:
        """Execute WAIT action"""
        wait_ms = action_data.get("waitAfterMs", 1000)
        label = action_data.get("label", "")

        result = {
            "id": action_index,
            "type": "WAIT",
            "waitMs": wait_ms,
            "label": label
        }

        try:
            logger.info(f"  [WAIT] For {wait_ms}ms")
            time.sleep(wait_ms / 1000.0)
            
            result["status"] = "success"
            result["message"] = f"Waited {wait_ms}ms"
            
            return result

        except Exception as e:
            logger.error(f"  [WAIT ERROR] {str(e)}")
            result["status"] = "error"
            result["message"] = str(e)[:200]
            return result
