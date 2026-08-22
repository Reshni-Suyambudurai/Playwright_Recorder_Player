"""
WebSocket event handler for routing and processing WebSocket events.
Angular Frontend
       │
       │ WebSocket JSON
       ▼
WebSocketHandler.handle_event()
       │
       ├── HELLO
       ├── START_RECORDING
       ├── CLICK_ACTION
       ├── TYPE_ACTION
       ├── SCROLL_ACTION
       ├── KEY_ACTION
       ├── PAGE_REFRESH
       ├── PAGE_BACK
       ├── STOP_RECORDING
       ├── SWITCH_TAB
       └── ...
"""
import asyncio
import time
import uuid
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("playwright_recorder.ws_handler")
from app.websocket.connection_manager import ConnectionManager
from app.websocket.websocket_events import EventType, HelloData, PongData, WelcomeData, ErrorData
from app.services.session_manager import SessionManager
from app.services.browser_service import BrowserService
from app.services.screenshot_service import ScreenshotService
from app.services.recording_storage import RecordingStorage
from app.services.dom_watcher import DomWatcher
from app.services.capture_manager import CaptureManager, CaptureReason, SettleStrategy
from app.services.database import DatabaseService
from app.services.assertion_service import AssertionService
from app.services.snapshot_service import SnapshotService
from app.models.recording import Recording, RecordingMeta, RecordingStep, AssertionStep, Coords, SelectorInfo, TargetMeta
from app.utils.selector_builder import build_selector
from app.utils import tab_manager


class WebSocketHandler:
    """
    Handles WebSocket events and routes them to appropriate handlers.
    """
    
    def __init__(self, connection_manager: ConnectionManager, session_manager: SessionManager,
                 browser_service: BrowserService, screenshot_service: ScreenshotService,
                 db: DatabaseService | None = None):
        self.connection_manager = connection_manager
        self.session_manager = session_manager
        self.browser_service = browser_service
        self.screenshot_service = screenshot_service
        self.recording_storage = RecordingStorage()
        self.db = db
        # Stateless — one shared instance reused across every hover/snapshot event
        self.assertion_service = AssertionService()
        self.snapshot_service = SnapshotService()
    
    async def handle_hello(self, session_id: str, websocket, data: dict) -> dict:
        """Handle HELLO — validates session, registers client_id mapping, replies WELCOME."""
        try:
            client_id = data.get("client_id")
            
            if not client_id:
                return self._error_response("INVALID_CLIENT_ID", "client_id is required in HELLO event")
            
            # Register the client_id → WebSocket mapping so future responses can be targeted
            self.connection_manager.register_client(session_id, client_id, websocket)
            
            welcome_data = {
                "session_id": session_id,
                "client_id": client_id,
                "message": "Connected to recording session",
                "timestamp": datetime.now().isoformat(),
                "connection_count": self.connection_manager.get_connection_count(session_id)
            }
            
            return {
                "event_type": EventType.WELCOME,
                "data": welcome_data,
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return self._error_response("HELLO_ERROR", str(e))
    
    async def handle_ping(self, session_id: str, data: dict) -> dict:
        """
        Handle PING event from client.
        
        Responds with PONG event containing timestamps for latency measurement.
        
        Args:
            session_id: The session ID
            data: Event data (may contain client timestamp)
            
        Returns:
            Response message dict with PONG event
        """
        try:
            client_timestamp = data.get("timestamp")
            server_timestamp = datetime.now().isoformat()
            
            pong_data = {
                "client_timestamp": client_timestamp,
                "server_timestamp": server_timestamp,
                "received_at": server_timestamp
            }
            
            return {
                "event_type": EventType.PONG,
                "data": pong_data,
                "timestamp": server_timestamp
            }
        
        except Exception as e:
            return self._error_response("PING_ERROR", str(e))
    
    async def handle_pong(self, session_id: str, data: dict) -> None:
        """
        Handle PONG event from client.
        
        This is a client response to server ping. Just log and track.
        
        Args:
            session_id: The session ID
            data: Event data from client
        """
        try:
            client_timestamp = data.get("timestamp")
            server_received_at = datetime.now().isoformat()
            
            print(f"[{session_id}] PONG received - Client timestamp: {client_timestamp}, Server received at: {server_received_at}")
        
        except Exception as e:
            print(f"Error handling PONG: {str(e)}")
    
    async def handle_navigate(self, session_id: str, data: dict) -> dict:
        """
        Handle NAVIGATE event from client.
        
        Navigates the browser to the specified URL.
        
        Args:
            session_id: The session ID
            data: Event data containing url
            
        Returns:
            Response message dict with NAVIGATION_SUCCESS or NAVIGATION_ERROR
        """
        try:
            url = data.get("url")
            
            if not url:
                return self._error_response("INVALID_URL", "url is required in NAVIGATE event")
            
            # Get session from session manager
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._create_navigation_error(url, "SESSION_NOT_FOUND", "Session does not exist")
            
            # Get page from session
            if not session.page:
                return self._create_navigation_error(url, "NO_PAGE", "No active page in session")
            
            # Navigate to URL
            result = await self.browser_service.navigate_to_url(session.page, url)
            
            # Update session current_url
            session.current_url = result["url"]
            
            # Create success response
            return {
                "event_type": EventType.NAVIGATION_SUCCESS,
                "data": {
                    "url": result["url"],
                    "title": result.get("title"),
                    "status_code": result.get("status_code")
                },
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            return self._create_navigation_error(data.get("url", "unknown"), "NAVIGATION_FAILED", str(e))
    
    async def handle_start_recording(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle START_RECORDING — navigate the browser, attach DomWatcher,
        take first screenshot and return RECORDING_STARTED.
        """
        try:
            t0 = time.perf_counter()
            url = data.get("url")
            recording_name = data.get("recording_name", "Untitled")
            description = data.get("description", "")
            intent = data.get("intent", "")
            logger.info("[WS START_RECORDING] start session=%s client=%s url=%s", session_id, client_id, url)

            if not url:
                return self._error_response("INVALID_URL", "url is required in START_RECORDING")

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            # Detach any existing watcher before starting fresh
            if session.dom_watcher:
                await session.dom_watcher.detach()

            # Navigate
            t_nav = time.perf_counter()
            result = await self.browser_service.navigate_to_url(session.page, url)
            session.current_url = result["url"]
            logger.info("[WS START_RECORDING] navigation done in %dms", int((time.perf_counter() - t_nav) * 1000))

            # Create per-session CaptureManager then attach DomWatcher to it
            cap_mgr = CaptureManager(self.screenshot_service, session_id, client_id)
            session.capture_manager = cap_mgr
            watcher = DomWatcher(cap_mgr)
            t_attach = time.perf_counter()
            await watcher.attach(session.page, session_id, client_id)
            session.dom_watcher = watcher
            logger.info("[WS START_RECORDING] dom watcher attached in %dms", int((time.perf_counter() - t_attach) * 1000))

            # Initialise recording state
            session.recording_id = str(uuid.uuid4())
            session.recording_name = recording_name
            session.recording_description = description
            session.recording_intent = intent
            session.recording_steps = []
            session.tabs = {}
            session.tab_watchers = {}
            session.tab_meta = {}

            # Register first tab
            tab_manager.register_tab(session, session.page, "tab-1")
            session.active_tab_id = "tab-1"
            session.tab_watchers["tab-1"] = watcher

            # Listen for new browser tabs opened by the page
            session.browser_context.on(
                "page",
                lambda new_page: asyncio.ensure_future(
                    self._on_new_tab(new_page, session_id, client_id)
                ),
            )

            # Append NAVIGATE as first step
            nav_step = RecordingStep(
                id=1,
                type="NAVIGATE",
                url=result["url"],
                pageUrl=result["url"],
                pageTitle=result.get("title"),
                waitAfterMs=100,
                tab_id="tab-1",
            )
            session.recording_steps.append(nav_step)

            # Push the first frame immediately
            t_frame = time.perf_counter()
            await cap_mgr.request(session.page, CaptureReason.MANUAL)
            logger.info("[WS START_RECORDING] first frame requested in %dms", int((time.perf_counter() - t_frame) * 1000))

            logger.info("[WS START_RECORDING] completed session=%s total=%dms", session_id, int((time.perf_counter() - t0) * 1000))

            return {
                "event_type": EventType.RECORDING_STARTED,
                "data": {
                    "recording_name": recording_name,
                    "url": result["url"],
                    "title": result.get("title"),
                    "timestamp": datetime.now().isoformat(),
                },
            }
        except Exception as e:
            logger.error("[WS START_RECORDING] failed session=%s: %s", session_id, e, exc_info=True)
            return self._error_response("START_RECORDING_ERROR", str(e))

    async def handle_click_action(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle CLICK_ACTION.
        If element at (x,y) is a text input → return INPUT_DETECTED (no click).
        Otherwise perform click, record CLICK step, capture frame.
        """
        try:
            x = data.get("x")
            y = data.get("y")
            button = data.get("button", "left")

            if x is None or y is None:
                return self._error_response("INVALID_COORDS", "x and y are required in CLICK_ACTION")

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            # Inspect element before clicking
            page = tab_manager.get_active_page(session) or session.page
            sel_info = await build_selector(page, int(x), int(y))

            # Capture page state BEFORE the click — navigation after click
            # can make page.title() throw, causing the step to be skipped.
            pre_click_url   = session.current_url
            try:
                pre_click_title = await page.title()
            except Exception:
                pre_click_title = ""

            # Right-clicks always fire directly — never trigger the input overlay
            if button == "left" and sel_info and sel_info.get("is_input"):
                # Don't click — ask frontend to open the input overlay
                return {
                    "event_type": EventType.INPUT_DETECTED,
                    "data": {
                        "x": x, "y": y,
                        "tag": sel_info.get("tag"),
                        "input_type": sel_info.get("input_type"),
                        "label": sel_info.get("label"),
                        "placeholder": sel_info.get("placeholder"),
                        "current_value": sel_info.get("current_value", ""),
                        "is_password": sel_info.get("is_password", False),
                        "selector": sel_info.get("selector"),
                    },
                }

            # Perform click (left or right)
            t0 = time.perf_counter()
            logger.info(f"[▶ CLICK] event received — ({x},{y}) button={button}")
            await self.browser_service.perform_click(page, int(x), int(y), button)
            logger.info(f"[▶ CLICK] browser click done in {int((time.perf_counter()-t0)*1000)}ms")

            # Record step — isolated so mid-navigation page.title() error cannot
            # prevent ACTION_DONE from being sent to the frontend
            if session.recording_steps is not None:
                try:
                    step_id = len(session.recording_steps) + 1
                    step = RecordingStep(
                        id=step_id,
                        type="CLICK",
                        pageUrl=pre_click_url,
                        pageTitle=pre_click_title,
                        coords=Coords(x=int(x), y=int(y)),
                        button=button,
                        waitAfterMs=300,
                        label=sel_info.get("label") if sel_info else None,
                        selector=SelectorInfo(**sel_info["selector"]) if sel_info and sel_info.get("selector") else None,
                        targetMeta=TargetMeta(**sel_info["target_meta"]) if sel_info and sel_info.get("target_meta") else None,
                        tab_id=session.active_tab_id or "tab-1",
                    )
                    session.recording_steps.append(step)
                except Exception as record_err:
                    logger.warning(f"[⚠ CLICK] step recording skipped: {record_err}")

            # Fire screenshot in background — ACTION_DONE returns immediately
            cap_mgr = session.capture_manager
            if cap_mgr:
                asyncio.ensure_future(cap_mgr.request(page, CaptureReason.ACTION_CLICK))
            logger.info(f"[✅ CLICK DONE] ACTION_DONE sent — {int((time.perf_counter()-t0)*1000)}ms after click (frame pending)")

            return {
                "event_type": EventType.ACTION_DONE,
                "data": {"type": "click", "x": x, "y": y, "success": True},
            }
        except Exception as e:
            return self._error_response("CLICK_ACTION_ERROR", str(e))

    async def handle_type_action(self, session_id: str, client_id: str, data: dict) -> dict:
        """Handle TYPE_ACTION — fill input field with text from the overlay."""
        try:
            text = data.get("text", "")
            x = data.get("x")
            y = data.get("y")
            selector = data.get("selector")
            is_password = data.get("is_password", False)
            label = data.get("label")
            tag = data.get("tag", "input")
            input_validation = data.get("inputValidation")

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            t0 = time.perf_counter()
            logger.info(f"[▶ TYPE] event received — text len={len(text)}")
            page = tab_manager.get_active_page(session) or session.page
            await self.browser_service.perform_type(page, selector or {}, text)
            logger.info(f"[▶ TYPE] browser type done in {int((time.perf_counter()-t0)*1000)}ms")

            # Record step
            if session.recording_steps is not None:
                page_url = session.current_url
                page_title = await page.title()
                step_id = len(session.recording_steps) + 1
                step = RecordingStep(
                    id=step_id,
                    type="TYPE",
                    pageUrl=page_url,
                    pageTitle=page_title,
                    coords=Coords(x=int(x), y=int(y)) if x is not None and y is not None else None,
                    text="{{password}}" if is_password else text,
                    label=label,
                    isPassword=is_password,
                    storeValue=True,
                    inputValidation=input_validation,
                    selector=SelectorInfo(**selector) if selector else None,
                    tab_id=session.active_tab_id or "tab-1",
                )
                session.recording_steps.append(step)

            # Fire screenshot in background — ACTION_DONE returns immediately
            cap_mgr = session.capture_manager
            if cap_mgr:
                asyncio.ensure_future(cap_mgr.request(page, CaptureReason.ACTION_TYPE))
            logger.info(f"[✅ TYPE DONE] ACTION_DONE sent — {int((time.perf_counter()-t0)*1000)}ms after type (frame pending)")

            return {"event_type": EventType.ACTION_DONE, "data": {"type": "type", "success": True}}
        except Exception as e:
            return self._error_response("TYPE_ACTION_ERROR", str(e))

    async def handle_scroll_action(self, session_id: str, client_id: str, data: dict) -> dict:
        """Handle SCROLL_ACTION — scroll the page and record step."""
        try:
            x = data.get("x", 0)
            y = data.get("y", 0)
            delta_x = data.get("delta_x", 0)
            delta_y = data.get("delta_y", 0)

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            t0 = time.perf_counter()
            logger.info(f"[▶ SCROLL] event received — ({x},{y}) delta=({delta_x},{delta_y})")
            page = tab_manager.get_active_page(session) or session.page
            await self.browser_service.perform_scroll(page, int(x), int(y), delta_x, delta_y)
            logger.info(f"[▶ SCROLL] browser scroll done in {int((time.perf_counter()-t0)*1000)}ms")

            # Record step
            if session.recording_steps is not None:
                step_id = len(session.recording_steps) + 1
                step = RecordingStep(
                    id=step_id,
                    type="SCROLL",
                    pageUrl=session.current_url,
                    coords=Coords(x=int(x), y=int(y)),
                    deltaX=delta_x,
                    deltaY=delta_y,
                    waitAfterMs=100,
                    tab_id=session.active_tab_id or "tab-1",
                )
                session.recording_steps.append(step)

            # Fire screenshot in background — ACTION_DONE returns immediately
            cap_mgr = session.capture_manager
            if cap_mgr:
                asyncio.ensure_future(cap_mgr.request(page, CaptureReason.ACTION_SCROLL))
            logger.info(f"[ SCROLL DONE] ACTION_DONE sent — {int((time.perf_counter()-t0)*1000)}ms after scroll (frame pending)")

            return {"event_type": EventType.ACTION_DONE, "data": {"type": "scroll", "success": True}}
        except Exception as e:
            return self._error_response("SCROLL_ACTION_ERROR", str(e))

    async def handle_key_action(self, session_id: str, client_id: str, data: dict) -> dict:
        """Handle KEY_ACTION — press Enter / Tab / Escape."""
        try:
            key = data.get("key", "Enter")
            allowed = {"Enter", "Tab", "Escape", "Backspace", "ArrowUp", "ArrowDown"}
            if key not in allowed:
                return self._error_response("INVALID_KEY", f"Key '{key}' not allowed")

            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session or page")

            t0 = time.perf_counter()
            logger.info(f"[▶ KEY] event received — key={key}")
            page = tab_manager.get_active_page(session) or session.page
            await self.browser_service.perform_key(page, key)
            logger.info(f"[▶ KEY] browser key done in {int((time.perf_counter()-t0)*1000)}ms")

            if session.recording_steps is not None:
                step_id = len(session.recording_steps) + 1
                step = RecordingStep(
                    id=step_id,
                    type="KEY",
                    pageUrl=session.current_url,
                    text=key,
                    tab_id=session.active_tab_id or "tab-1",
                )
                session.recording_steps.append(step)

            # Fire screenshot in background — ACTION_DONE returns immediately
            cap_mgr = session.capture_manager
            if cap_mgr:
                reason = CaptureReason.ACTION_CLICK if key == "Enter" else CaptureReason.ACTION_TYPE
                asyncio.ensure_future(cap_mgr.request(page, reason))
            logger.info(f"[ KEY DONE] ACTION_DONE sent — {int((time.perf_counter()-t0)*1000)}ms after key (frame pending)")
            return {"event_type": EventType.ACTION_DONE, "data": {"type": "key", "success": True}}
        except Exception as e:
            return self._error_response("KEY_ACTION_ERROR", str(e))

    async def _capture_after_nav(self, page, session_id: str, client_id: str, session, step_type: str) -> None:
        """Wait for page to settle then record a NAVIGATE step and send a screenshot."""
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        session.current_url = page.url
        if session.recording_steps is not None:
            step_id = len(session.recording_steps) + 1
            session.recording_steps.append(RecordingStep(
                id=step_id,
                type="NAVIGATE",
                url=session.current_url,
                pageUrl=session.current_url,
                pageTitle=await page.title(),
                waitAfterMs=100,
                tab_id=session.active_tab_id or "tab-1",
            ))
            logger.info(f"[NAV] Recorded NAVIGATE step {step_id} ({step_type}) url={session.current_url}")
        sent = await self.screenshot_service.capture_and_send(page, session_id, client_id)
        logger.info(f"[NAV] capture_and_send result={sent}")

    async def handle_page_refresh(self, session_id: str, client_id: str) -> dict:
        """Handle PAGE_REFRESH — reload the current page."""
        logger.info(f"[REFRESH] start session={session_id} client={client_id}")
        session = self.session_manager.get_session(session_id)
        if not session or not session.page:
            return self._error_response("SESSION_NOT_FOUND", "No active session or page")
        page = tab_manager.get_active_page(session) or session.page
        try:
            try:
                logger.info("[REFRESH] calling page.reload()")
                await page.reload(wait_until="load", timeout=30000)
                logger.info("[REFRESH] reload complete")
            except BaseException as ex:
                logger.warning(f"[REFRESH] reload error (continuing): {type(ex).__name__}: {ex}")
            await self._capture_after_nav(page, session_id, client_id, session, "refresh")
            logger.info("[REFRESH] done")
            return {"event_type": EventType.ACTION_DONE, "data": {"type": "refresh", "success": True}}
        except BaseException as e:
            logger.error(f"[REFRESH] outer error: {type(e).__name__}: {e}", exc_info=True)
            await self.screenshot_service.capture_and_send(page, session_id, client_id)
            return self._error_response("PAGE_REFRESH_ERROR", str(e))

    async def handle_page_back(self, session_id: str, client_id: str) -> dict:
        """Handle PAGE_BACK — navigate to the previous browser history entry."""
        logger.info(f"[BACK] start session={session_id} client={client_id}")
        session = self.session_manager.get_session(session_id)
        if not session or not session.page:
            return self._error_response("SESSION_NOT_FOUND", "No active session or page")
        page = tab_manager.get_active_page(session) or session.page
        try:
            try:
                logger.info("[BACK] calling page.go_back()")
                await page.go_back(wait_until="load", timeout=10000)
                logger.info("[BACK] go_back complete")
            except BaseException as ex:
                logger.warning(f"[BACK] go_back error (continuing): {type(ex).__name__}: {ex}")
            await self._capture_after_nav(page, session_id, client_id, session, "back")
            logger.info("[BACK] done")
            return {"event_type": EventType.ACTION_DONE, "data": {"type": "back", "success": True}}
        except BaseException as e:
            logger.error(f"[BACK] outer error: {type(e).__name__}: {e}", exc_info=True)
            await self.screenshot_service.capture_and_send(page, session_id, client_id)
            return self._error_response("PAGE_BACK_ERROR", str(e))

    async def handle_stop_recording(self, session_id: str, client_id: str) -> dict:
        """Handle STOP_RECORDING — serialize steps, save JSON, return step list."""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            # Detach watchers across all tabs first.
            await tab_manager.detach_all_watchers(session)
            # Backward-compat: if a legacy singleton watcher is still present, detach it too.
            if session.dom_watcher:
                await session.dom_watcher.detach()
                session.dom_watcher = None

            # Build Recording object
            meta = RecordingMeta(
                id=session.recording_id or str(uuid.uuid4()),
                title=session.recording_name or "Untitled",
                description=getattr(session, "recording_description", ""),
                intent=getattr(session, "recording_intent", ""),
            )
            recording = Recording(meta=meta)
            for step in (session.recording_steps or []):
                recording.add_step(step)

            # Save to disk (file-based, kept as backup)
            self.recording_storage.save(recording)

            # Save to SQLite database
            if self.db:
                recording_dict = {
                    "version": recording.version,
                    "meta": recording.meta.model_dump(by_alias=True),
                    "steps": recording.steps,
                }
                await self.db.ensure_user(client_id)
                await self.db.save_recording(
                    record_id=meta.id,
                    client_id=client_id,
                    recording_json=recording_dict,
                    flow_name=meta.title,
                )

            # Build step summary list for frontend display
            steps_summary = [
                {
                    "id": s.id,
                    "type": s.type,
                    "label": self._step_summary_label(s),
                    "pageUrl": s.page_url,
                    "timestamp": s.timestamp,
                }
                for s in (session.recording_steps or [])
            ]

            # Reset recording state
            session.recording_steps = []
            session.recording_id = ""
            session.recording_name = ""

            return {
                "event_type": EventType.RECORDING_STOPPED,
                "data": {
                    "recording_id": meta.id,
                    "recording_name": meta.title,
                    "step_count": recording.step_count(),
                    "steps": steps_summary,
                },
            }
        except Exception as e:
            return self._error_response("STOP_RECORDING_ERROR", str(e))

    async def _on_new_tab(self, new_page, session_id: str, client_id: str) -> None:
        """Called when browser_context fires a 'page' event (new tab opened)."""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return

            await new_page.wait_for_load_state("domcontentloaded", timeout=10000)

            tab_id = tab_manager.next_tab_id(session)
            tab_manager.register_tab(session, new_page, tab_id)

            # Mark the triggering step as isTriggerNewTab=True
            if session.recording_steps:
                session.recording_steps[-1].is_trigger_new_tab = True

            # Attach DomWatcher for new tab
            if not session.capture_manager:
                session.capture_manager = CaptureManager(self.screenshot_service, session_id, client_id)
            watcher = DomWatcher(session.capture_manager)
            await watcher.attach(new_page, session_id, client_id)
            session.tab_watchers[tab_id] = watcher

            title = await new_page.title()
            url = new_page.url
            session.tab_meta[tab_id] = {"title": title, "url": url}

            # Auto-switch to new tab
            session.active_tab_id = tab_id

            # Append NAVIGATE step for the new tab
            step_id = len(session.recording_steps) + 1
            session.recording_steps.append(RecordingStep(
                id=step_id, type="NAVIGATE",
                url=url, pageUrl=url, pageTitle=title,
                waitAfterMs=100, tab_id=tab_id,
            ))

            # Notify frontend
            tab_list = [
                {"tab_id": tid, "title": m.get("title", ""), "url": m.get("url", ""), "active": tid == tab_id}
                for tid, m in session.tab_meta.items()
            ]
            await self.connection_manager.send_to_client(session_id, client_id, {
                "event_type": EventType.TAB_OPENED,
                "data": {
                    "tab_id": tab_id, "title": title, "url": url,
                    "active": True, "tabs": tab_list,
                },
            })
            # Send first frame of new tab
            await self.screenshot_service.capture_and_send(new_page, session_id, client_id)
        except Exception as e:
            logger.error(f"_on_new_tab error: {e}", exc_info=True)

    async def handle_switch_tab(self, session_id: str, client_id: str, data: dict) -> dict:
        """Switch active tab and send a fresh frame."""
        try:
            tab_id = data.get("tab_id")
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            page = tab_manager.switch_tab(session, tab_id)
            if not page:
                return self._error_response("TAB_NOT_FOUND", f"Tab '{tab_id}' not found")

            title = await page.title()
            url = page.url
            session.tab_meta[tab_id] = {"title": title, "url": url}

            tab_list = [
                {"tab_id": tid, "title": m.get("title", ""), "url": m.get("url", ""), "active": tid == tab_id}
                for tid, m in session.tab_meta.items()
            ]
            await self.screenshot_service.capture_and_send(page, session_id, client_id)
            return {
                "event_type": EventType.TAB_SWITCHED,
                "data": {"tab_id": tab_id, "title": title, "url": url, "tabs": tab_list},
            }
        except Exception as e:
            return self._error_response("SWITCH_TAB_ERROR", str(e))

    async def handle_assertion_mode_toggled(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle assertion mode toggle (visibility, text, value, snapshot, or null).
        Store the active mode in session state.
        """
        try:
            mode = data.get("mode")  # "visibility" | "text" | "value" | "snapshot" | null
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            # Validate mode
            if mode not in [None, "visibility", "text", "value", "snapshot"]:
                return self._error_response("INVALID_MODE", f"Unknown assertion mode: {mode}")

            # Store in session (will be used during hover to determine what to extract)
            session.assertion_mode = mode
            logger.debug(f"[ASSERTION] session={session_id} mode_toggled={mode}")

            return {
                "event_type": EventType.ASSERTION_MODE_TOGGLED,
                "data": {"mode": mode, "status": "ok"},
            }
        except Exception as e:
            return self._error_response("ASSERTION_MODE_ERROR", str(e))

    async def handle_assertion_hover(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle assertion hover: inspect element at (x, y) and emit ASSERTION_DISCOVERED.
        Uses the assertion mode stored in session to filter data.
        """
        try:
            x = data.get("x")
            y = data.get("y")
            session = self.session_manager.get_session(session_id)
            
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            page = tab_manager.get_active_page(session) or session.page

            if x is None or y is None:
                return self._error_response("INVALID_COORDS", "x, y coordinates required")

            # Validate that assertion mode is active
            if not session.assertion_mode:
                return self._error_response("MODE_INACTIVE", "No assertion mode is active")

            # Discover and filter based on mode
            assertion_data = await self.assertion_service.discover_by_mode(
                page, x, y, session.assertion_mode
            )

            # Send async ASSERTION_DISCOVERED event to client
            discovery_event = {
                "event_type": EventType.ASSERTION_DISCOVERED,
                "data": {
                    "mode": session.assertion_mode,
                    "assertionData": assertion_data,
                    "coords": {"x": x, "y": y},
                    "pageUrl": page.url,
                }
            }
            await self.connection_manager.send_to_client(session_id, client_id, discovery_event)

            # Return empty response (event already sent)
            return {}

        except Exception as e:
            logger.error(f"[ASSERTION_HOVER] session={session_id}: {e}", exc_info=True)
            return self._error_response("ASSERTION_HOVER_ERROR", str(e))

    async def handle_snapshot_capture_request(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle snapshot capture request: capture ARIA snapshot in rectangular region.
        """
        try:
            x = data.get("x")
            y = data.get("y")
            width = data.get("width")
            height = data.get("height")
            
            session = self.session_manager.get_session(session_id)
            if not session or not session.page:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            page = tab_manager.get_active_page(session) or session.page

            if x is None or y is None or width is None or height is None:
                return self._error_response("INVALID_COORDS", "x, y, width, height required")

            # Validate that snapshot mode is active
            if session.assertion_mode != "snapshot":
                return self._error_response("MODE_INACTIVE", "Snapshot mode is not active")

            # Capture ARIA snapshot
            snapshot_data = await self.snapshot_service.capture_aria_snapshot(page, x, y, width, height)

            # Send SNAPSHOT_PREVIEW event to client
            preview_event = {
                "event_type": EventType.SNAPSHOT_PREVIEW,
                "data": {
                    "label": snapshot_data.get("label", "Selected region"),
                    "ariaSnapshot": snapshot_data.get("ariaSnapshot", ""),
                    "elementCount": snapshot_data.get("elementCount", 0),
                    "region": {"x": x, "y": y, "width": width, "height": height},
                    "pageUrl": page.url,
                }
            }
            await self.connection_manager.send_to_client(session_id, client_id, preview_event)

            # Return empty response (event already sent)
            return {}

        except Exception as e:
            logger.error(f"[SNAPSHOT_CAPTURE] session={session_id}: {e}", exc_info=True)
            return self._error_response("SNAPSHOT_CAPTURE_ERROR", str(e))

    def _step_summary_label(self, step: RecordingStep | AssertionStep) -> str:
        """Human-readable label for the RECORDING_STOPPED step summary sent to the frontend."""
        if isinstance(step, AssertionStep):
            return step.label or f"{step.assertion_type} assertion"
        if step.label:
            return step.label
        if step.text:
            return step.text
        if step.url:
            return step.url
        if step.coords:
            return f"({step.coords.x},{step.coords.y})"
        return step.type

    def _build_assertion_step(
        self,
        session,
        assertion_type: str,
        raw_data: Dict[str, Any],
        coords: dict | None,
        page_url: str | None,
        page_title: str | None,
        label: str | None = None,
    ) -> AssertionStep:
        """
        Build an AssertionStep from mode-specific data (as returned by AssertionService /
        SnapshotService). `selector` and `mode` — if present in raw_data — become their own
        fields instead of being duplicated inside discoveredData.

        Shared by handle_assertion_save (visibility/text/value) and
        handle_snapshot_save_assertion (snapshot) so both save paths produce identical,
        playback-ready step shapes.
        """
        selector = raw_data.get("selector")
        discovered_data = {k: v for k, v in raw_data.items() if k not in ("mode", "selector")}
        return AssertionStep(
            id=len(session.recording_steps) + 1,
            assertionType=assertion_type,
            selector=SelectorInfo(**selector) if selector else None,
            coords=Coords(**coords) if coords else None,
            discoveredData=discovered_data,
            pageUrl=page_url,
            pageTitle=page_title,
            label=label,
            tab_id=session.active_tab_id or "tab-1",
        )

    async def _send_assertion_saved(self, session_id: str, client_id: str, assertion_type: str) -> None:
        await self.connection_manager.send_to_client(session_id, client_id, {
            "event_type": EventType.ASSERTION_SAVED,
            "data": {"type": assertion_type, "timestamp": datetime.now().isoformat()},
        })

    async def handle_assertion_save(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle ASSERTION_STEP_RECORDED: persist a visibility/text/value assertion
        (captured via hover, pinned by click) as a recording step.
        """
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            mode = data.get("mode")
            assertion_data = data.get("data") or {}
            if not mode or not assertion_data:
                return self._error_response("INVALID_ASSERTION", "mode and data are required")

            page = tab_manager.get_active_page(session) or session.page
            page_title = await page.title() if page else None

            if session.recording_steps is not None:
                step = self._build_assertion_step(
                    session,
                    assertion_type=mode,
                    raw_data=assertion_data,
                    coords=data.get("coords"),
                    page_url=data.get("pageUrl") or session.current_url,
                    page_title=page_title,
                )
                session.recording_steps.append(step)

            await self._send_assertion_saved(session_id, client_id, mode)
            return {}

        except Exception as e:
            logger.error(f"[ASSERTION_SAVE] session={session_id}: {e}", exc_info=True)
            return self._error_response("ASSERTION_SAVE_ERROR", str(e))

    async def handle_snapshot_save_assertion(self, session_id: str, client_id: str, data: dict) -> dict:
        """
        Handle SNAPSHOT_SAVE_ASSERTION: persist the previewed ARIA snapshot as an assertion step.
        """
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return self._error_response("SESSION_NOT_FOUND", "No active session")

            label = data.get("label", "")
            page = tab_manager.get_active_page(session) or session.page
            raw_data = {
                "label": label,
                "ariaSnapshot": data.get("ariaSnapshot", ""),
                "elementCount": data.get("elementCount", 0),
                "region": data.get("region"),
            }

            if session.recording_steps is not None:
                step = self._build_assertion_step(
                    session,
                    assertion_type="snapshot",
                    raw_data=raw_data,
                    coords=None,
                    page_url=data.get("pageUrl") or (page.url if page else None),
                    page_title=await page.title() if page else None,
                    label=label,
                )
                session.recording_steps.append(step)

            await self._send_assertion_saved(session_id, client_id, "snapshot")
            return {}

        except Exception as e:
            logger.error(f"[SNAPSHOT_SAVE] session={session_id}: {e}", exc_info=True)
            return self._error_response("SNAPSHOT_SAVE_ERROR", str(e))

    async def handle_event(self, session_id: str, websocket, event_data: dict) -> None:
        """
        Route incoming event to the appropriate handler and send the response
        directly to the originating client via client_id targeting.
        """
        try:
            event_type = event_data.get("event_type")
            client_id = event_data.get("client_id")   # top-level field on every event
            data = event_data.get("data", {})
            logger.info(f"[WS-ROUTER] session={session_id} event_type={event_type!r}")

            if not event_type:
                response = self._error_response("NO_EVENT_TYPE", "event_type is required")
            elif event_type == EventType.HELLO:
                response = await self.handle_hello(session_id, websocket, data)
            elif event_type == EventType.PING:
                response = await self.handle_ping(session_id, data)
            elif event_type == EventType.PONG:
                await self.handle_pong(session_id, data)
                return  # no response for PONG
            elif event_type == EventType.NAVIGATE:
                response = await self.handle_navigate(session_id, data)
            elif event_type == EventType.START_RECORDING:
                response = await self.handle_start_recording(session_id, client_id, data)
            elif event_type == EventType.CLICK_ACTION:
                response = await self.handle_click_action(session_id, client_id, data)
            elif event_type == EventType.TYPE_ACTION:
                response = await self.handle_type_action(session_id, client_id, data)
            elif event_type == EventType.SCROLL_ACTION:
                response = await self.handle_scroll_action(session_id, client_id, data)
            elif event_type == EventType.KEY_ACTION:
                response = await self.handle_key_action(session_id, client_id, data)
            elif event_type == EventType.PAGE_REFRESH:
                response = await self.handle_page_refresh(session_id, client_id)
            elif event_type == EventType.PAGE_BACK:
                response = await self.handle_page_back(session_id, client_id)
            elif event_type == EventType.STOP_RECORDING:
                response = await self.handle_stop_recording(session_id, client_id)
            elif event_type == EventType.SWITCH_TAB:
                response = await self.handle_switch_tab(session_id, client_id, data)
            elif event_type == EventType.ASSERTION_MODE_TOGGLED:
                response = await self.handle_assertion_mode_toggled(session_id, client_id, data)
            elif event_type == EventType.ASSERTION_HOVER:
                response = await self.handle_assertion_hover(session_id, client_id, data)
            elif event_type == EventType.SNAPSHOT_CAPTURE_REQUEST:
                response = await self.handle_snapshot_capture_request(session_id, client_id, data)
            elif event_type == EventType.SNAPSHOT_SAVE_ASSERTION:
                response = await self.handle_snapshot_save_assertion(session_id, client_id, data)
            elif event_type == EventType.ASSERTION_STEP_RECORDED:
                response = await self.handle_assertion_save(session_id, client_id, data)
            else:
                response = self._error_response("UNKNOWN_EVENT", f"Unknown event type: {event_type}")

            if response:
                # Send to the specific client if we know their ID, else fall back to the socket
                if client_id:
                    sent = await self.connection_manager.send_to_client(session_id, client_id, response)
                    if not sent:
                        # client not registered yet (e.g. HELLO itself) — reply directly
                        await websocket.send_json(response)
                else:
                    await websocket.send_json(response)

        except Exception as e:
            error = self._error_response("EVENT_HANDLER_ERROR", str(e))
            await websocket.send_json(error)
    
    def _error_response(self, error_code: str, message: str) -> dict:
        """
        Create an error response.
        
        Args:
            error_code: Error code
            message: Error message
            
        Returns:
            Error response dict
        """
        return {
            "event_type": EventType.ERROR,
            "data": {
                "error": error_code,
                "message": message
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def _create_navigation_error(self, url: str, error_code: str, message: str) -> dict:
        """
        Create a navigation error response.
        
        Args:
            url: The URL that failed to navigate
            error_code: Error code
            message: Error message
            
        Returns:
            Navigation error response dict
        """
        return {
            "event_type": EventType.NAVIGATION_ERROR,
            "data": {
                "url": url,
                "error": error_code,
                "message": message
            },
            "timestamp": datetime.now().isoformat()
        }

