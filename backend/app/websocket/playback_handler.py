"""
WebSocket handler for playback sessions (/ws/play/{play_id}).
Mirrors the structure of WebSocketHandler but for playback lifecycle.

It receives messages and decides who should handle them.

PlaybackHandler is the WebSocket controller for the Player. 
It receives all real-time messages from the frontend during playback, routes them to the appropriate handler, controls pause/resume/stop actions, and communicates with the browser and frontend.
Frontend
   │
   ▼
PlaybackHandler.handle_event()
   │
   ├── HELLO
   ├── PLAY_RESUME
   ├── PLAY_STOP
   ├── PAUSE_CLICK
   ├── PAUSE_SCROLL
   ├── PAUSE_TYPE
   └── PING
"""
import asyncio
import logging
import time
from datetime import datetime
from pydantic import ValidationError

from app.models.playback import PlaySession, PlayStatus
from app.models.playback_contracts import (
    PlaybackEventEnvelope,
    PlaybackHelloData,
    PlaybackPatchStepsData,
    PlaybackPauseClickData,
    PlaybackPauseScrollData,
    PlaybackPauseTypeData,
)
from app.models.recording import RecordingStep, SelectorInfo

from app.services.playback_service import PlaybackService
from app.services.browser_service import BrowserService
from app.services.capture_manager import CaptureReason
from app.utils.selector_builder import build_selector
from app.websocket.connection_manager import ConnectionManager

logger = logging.getLogger("playwright_recorder.ws.playback")


class PlaybackHandler:
    def __init__(
        self,
        connection_manager: ConnectionManager,
        playback_service: PlaybackService,
        browser_service: BrowserService,
    ):
        self._connection_manager = connection_manager
        self._playback_service   = playback_service
        self._browser_service    = browser_service

    async def handle_event(
        self,
        play_id: str,
        websocket,
        session: PlaySession,
        event: dict,
    ) -> None:
        try:
            envelope = PlaybackEventEnvelope.model_validate(event)
        except ValidationError as exc:
            await websocket.send_json({
                "event_type": "ERROR",
                "data": {"error": f"Invalid payload: {exc.errors()}"},
            })
            return

        event_type = envelope.event_type
        data = envelope.data

        if event_type == "HELLO":
            try:
                hello_data = PlaybackHelloData.model_validate(data)
            except ValidationError as exc:
                await websocket.send_json({
                    "event_type": "ERROR",
                    "data": {"error": f"Invalid HELLO payload: {exc.errors()}"},
                })
                return
            await self._handle_hello(play_id, websocket, session, hello_data)
        elif event_type == "PLAY_RESUME":
            self._handle_resume(session)
        elif event_type == "PLAY_STOP":
            await self._handle_stop(session)
        elif event_type == "PAUSE_CLICK":
            try:
                pause_click = PlaybackPauseClickData.model_validate(data)
            except ValidationError as exc:
                await websocket.send_json({
                    "event_type": "ERROR",
                    "data": {"error": f"Invalid PAUSE_CLICK payload: {exc.errors()}"},
                })
                return
            await self._handle_pause_click(play_id, session, pause_click)
        elif event_type == "PAUSE_SCROLL":
            try:
                pause_scroll = PlaybackPauseScrollData.model_validate(data)
            except ValidationError as exc:
                await websocket.send_json({
                    "event_type": "ERROR",
                    "data": {"error": f"Invalid PAUSE_SCROLL payload: {exc.errors()}"},
                })
                return
            await self._handle_pause_scroll(session, pause_scroll)
        elif event_type == "PAUSE_TYPE":
            try:
                pause_type = PlaybackPauseTypeData.model_validate(data)
            except ValidationError as exc:
                await websocket.send_json({
                    "event_type": "ERROR",
                    "data": {"error": f"Invalid PAUSE_TYPE payload: {exc.errors()}"},
                })
                return
            await self._handle_pause_type(session, pause_type)
        elif event_type == "PLAY_PATCH_STEPS":
            try:
                patch_data = PlaybackPatchStepsData.model_validate(data)
            except ValidationError as exc:
                await websocket.send_json({
                    "event_type": "ERROR",
                    "data": {"error": f"Invalid PLAY_PATCH_STEPS payload: {exc.errors()}"},
                })
                return
            await self._handle_patch_steps(play_id, session, patch_data)
        elif event_type == "PING":
            await self._connection_manager.send_to_client(play_id, session.client_id, {
                "event_type": "PONG",
                "data": {"timestamp": datetime.now().isoformat()},
            })
        else:
            logger.warning(f"[PLAY:{play_id}] unknown event_type: {event_type}")

    # ── HELLO — register client, kick off playback task ────────────────────
    async def _handle_hello(
        self,
        play_id: str,
        websocket,
        session: PlaySession,
        data: PlaybackHelloData,
    ) -> None:
        client_id = data.client_id
        if not client_id:
            await websocket.send_json({
                "event_type": "ERROR",
                "data": {"error": "client_id required in HELLO"},
            })
            return

        session.client_id = client_id
        self._connection_manager.register_client(play_id, client_id, websocket)

        await websocket.send_json({
            "event_type": "WELCOME",
            "data": {
                "play_session_id": play_id,
                "message": "Playback session ready — starting now",
                "timestamp": datetime.now().isoformat(),
            },
        })
        if session.task and not session.task.done():
            logger.info(f"[PLAY:{play_id}] HELLO from client {client_id} — playback task already running")
            return

        logger.info(f"[PLAY:{play_id}] HELLO from client {client_id} — starting playback task")

        # Launch playback as background task
        session.task = asyncio.create_task(
            self._playback_service.run_playback(session, play_id, client_id)
        )

    # ── PAUSE_CLICK — click or detect input during pause ───────────────────
    async def _handle_pause_click(self, play_id: str, session: PlaySession, data: PlaybackPauseClickData) -> None:
        if session.status != PlayStatus.PAUSED or not session.page:
            return
        x = data.x
        y = data.y
        if x is None or y is None:
            return

        # Inspect element — if it is an input, open the type overlay instead of clicking
        try:
            sel_info = await build_selector(session.page, int(x), int(y))
        except Exception:
            sel_info = None

        if sel_info and sel_info.get("is_input"):
            # Promote to PAUSE_INPUT_DETECTED — let frontend show type overlay
            await self._connection_manager.send_to_client(play_id, session.client_id, {
                "event_type": "PAUSE_INPUT_DETECTED",
                "data": {
                    "x": x,
                    "y": y,
                    "tag":           sel_info.get("tag"),
                    "input_type":    sel_info.get("input_type"),
                    "label":         sel_info.get("label"),
                    "placeholder":   sel_info.get("placeholder"),
                    "current_value": sel_info.get("current_value", ""),
                    "is_password":   sel_info.get("is_password", False),
                    "selector":      sel_info.get("selector"),
                },
            })
            logger.info(f"[PLAY:{play_id}] PAUSE_CLICK ({x},{y}) → input detected, opening type overlay")
            return

        # Not an input — perform the click
        try:
            await session.page.mouse.click(float(x), float(y))
            logger.info(f"[PLAY:{play_id}] PAUSE_CLICK ({x},{y})")
        except Exception as e:
            logger.warning(f"[PLAY:{play_id}] PAUSE_CLICK failed: {e}")
        
        # Capture as RecordingStep if pause recording enabled
        if session.enable_pause_recording and session.current_step_id > 0:
            try:
                page_url = session.page.url
                page_title = await session.page.title()
                
                # Build selector info from captured data
                selector = None
                target_meta = None
                if sel_info and sel_info.get("selector"):
                    selector_dict = sel_info.get("selector", {})
                    selector = SelectorInfo(
                        strategy=selector_dict.get("strategy", "css"),
                        value=selector_dict.get("value", ""),
                    )
                    # Capture target metadata
                    target_meta_dict = sel_info.get("target_meta", {})
                    if target_meta_dict:
                        from app.models.recording import TargetMeta
                        target_meta = TargetMeta(**target_meta_dict)
                
                # Create RecordingStep for this pause click
                pause_step = RecordingStep(
                    id=0,  # Will be re-indexed later
                    type="CLICK",
                    coords={"x": int(x), "y": int(y)},
                    button="left",
                    selector=selector,
                    target_meta=target_meta,
                    page_url=page_url,
                    page_title=page_title,
                    timestamp=int(time.time() * 1000),
                    should_run=True,
                    pause=False,
                    tab_id="tab-1",  # Default tab
                )
                
                # Add to insertion point for current step
                if session.current_step_id not in session.pause_step_insertion_points:
                    session.pause_step_insertion_points[session.current_step_id] = []
                session.pause_step_insertion_points[session.current_step_id].append(pause_step)
                
                logger.debug(f"[PLAY:{play_id}] Captured PAUSE_CLICK as step after step {session.current_step_id}")
            except Exception as e:
                logger.warning(f"[PLAY:{play_id}] Failed to capture pause step: {e}")
        
        if session.capture_manager:
            session.capture_manager.schedule_request(session.page, CaptureReason.PAUSE_CLICK)

    # ── PAUSE_SCROLL — perform a scroll during pause then capture ──────────
    async def _handle_pause_scroll(self, session: PlaySession, data: PlaybackPauseScrollData) -> None:
        if session.status != PlayStatus.PAUSED or not session.page:
            return
        x = data.x
        y = data.y
        delta_y = data.delta_y
        try:
            await session.page.mouse.wheel(delta_x=0, delta_y=float(delta_y))
            logger.info(f"[PLAY:{session.play_id}] PAUSE_SCROLL ({x},{y}) deltaY={delta_y}")
        except Exception as e:
            logger.warning(f"[PLAY:{session.play_id}] PAUSE_SCROLL failed: {e}")
        
        # Capture as RecordingStep if pause recording enabled
        if session.enable_pause_recording and session.current_step_id > 0:
            try:
                page_url = session.page.url
                page_title = await session.page.title()
                
                # Create RecordingStep for this pause scroll
                pause_step = RecordingStep(
                    id=0,  # Will be re-indexed later
                    type="SCROLL",
                    coords={"x": int(x), "y": int(y)},
                    delta_x=0.0,
                    delta_y=float(delta_y),
                    page_url=page_url,
                    page_title=page_title,
                    timestamp=int(time.time() * 1000),
                    should_run=True,
                    pause=False,
                    tab_id="tab-1",  # Default tab
                )
                
                # Add to insertion point for current step
                if session.current_step_id not in session.pause_step_insertion_points:
                    session.pause_step_insertion_points[session.current_step_id] = []
                session.pause_step_insertion_points[session.current_step_id].append(pause_step)
                
                logger.debug(f"[PLAY:{session.play_id}] Captured PAUSE_SCROLL as step after step {session.current_step_id}")
            except Exception as e:
                logger.warning(f"[PLAY:{session.play_id}] Failed to capture pause scroll step: {e}")
        
        if session.capture_manager:
            session.capture_manager.schedule_request(session.page, CaptureReason.PAUSE_SCROLL)

    # ── PAUSE_TYPE — type into a field during pause then capture ───────────
    async def _handle_pause_type(self, session: PlaySession, data: PlaybackPauseTypeData) -> None:
        if session.status != PlayStatus.PAUSED or not session.page:
            return
        selector = data.selector
        text     = data.text
        if not selector or text is None:
            return
        try:
            await self._browser_service.perform_type(session.page, selector, text)
            logger.info(f"[PLAY:{session.play_id}] PAUSE_TYPE selector={selector.get('strategy')}={selector.get('value')} len={len(text)}")
        except Exception as e:
            logger.warning(f"[PLAY:{session.play_id}] PAUSE_TYPE failed: {e}")
        
        # Capture as RecordingStep if pause recording enabled
        if session.enable_pause_recording and session.current_step_id > 0:
            try:
                page_url = session.page.url
                page_title = await session.page.title()
                
                # Build selector info
                selector_obj = None
                if selector:
                    selector_obj = SelectorInfo(
                        strategy=selector.get("strategy", "css"),
                        value=selector.get("value", ""),
                    )
                
                # Determine if text is password
                is_password = text.startswith("{{") and text.endswith("}}") if text else False
                
                # Create RecordingStep for this pause type
                pause_step = RecordingStep(
                    id=0,  # Will be re-indexed later
                    type="TYPE",
                    text=text,
                    selector=selector_obj,
                    is_password=is_password,
                    page_url=page_url,
                    page_title=page_title,
                    timestamp=int(time.time() * 1000),
                    should_run=True,
                    pause=False,
                    tab_id="tab-1",  # Default tab
                )
                
                # Add to insertion point for current step
                if session.current_step_id not in session.pause_step_insertion_points:
                    session.pause_step_insertion_points[session.current_step_id] = []
                session.pause_step_insertion_points[session.current_step_id].append(pause_step)
                
                logger.debug(f"[PLAY:{session.play_id}] Captured PAUSE_TYPE as step after step {session.current_step_id}")
            except Exception as e:
                logger.warning(f"[PLAY:{session.play_id}] Failed to capture pause type step: {e}")
        
        if session.capture_manager:
            session.capture_manager.schedule_request(session.page, CaptureReason.PAUSE_TYPE)

    async def _handle_patch_steps(self, play_id: str, session: PlaySession, data: PlaybackPatchStepsData) -> None:
        patches = [patch.model_dump(exclude_none=True) for patch in data.patches]

        if session.status not in (PlayStatus.PENDING, PlayStatus.RUNNING, PlayStatus.PAUSED):
            ack = {
                "receivedCount": len(patches),
                "appliedCount": 0,
                "unresolvedStepIds": [p.get("stepId") for p in patches if isinstance(p.get("stepId"), int)],
                "message": f"Playback is {session.status.value}; runtime changes can no longer be applied.",
            }
        else:
            ack = self._playback_service.apply_runtime_step_patches(session, patches)

        if session.client_id:
            await self._connection_manager.send_to_client(play_id, session.client_id, {
                "event_type": "PLAY_PATCH_STEPS_ACK",
                "data": ack,
            })

    # ── PLAY_RESUME — unblock a paused step ────────────────────────────────
    def _handle_resume(self, session: PlaySession) -> None:
        if session.status == PlayStatus.PAUSED:
            session.pause_event.set()
            logger.info(f"[PLAY:{session.play_id}] RESUME received")

    # ── PLAY_STOP — cancel the task ────────────────────────────────────────
    async def _handle_stop(self, session: PlaySession) -> None:
        if session.task and not session.task.done():
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass
        session.status = PlayStatus.STOPPED
        session.mark_finished()
        logger.info(f"[PLAY:{session.play_id}] STOPPED by client")
