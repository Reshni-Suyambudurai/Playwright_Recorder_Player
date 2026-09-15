"""
PlaybackEventEmitter — Decoupled event emission with MCP metadata enrichment.

Allows PlaybackService to emit events without knowing about FastAPI/WebSocket.
Both FastAPI and MCP clients consume the same event stream, with optional MCP metadata.
"""
import time
from typing import Any, Dict, Callable, Optional


class PlaybackEventEmitter:
    """
    Emits playback events with MCP response metadata.
    Allows both FastAPI and MCP clients to consume the same event stream.
    
    FastAPI listeners: Receive events and send via WebSocket
    MCP listeners: Receive events and broadcast via WebSocket event server
    """
    
    def __init__(self):
        self.listeners: list[Callable] = []
    
    async def emit(
        self,
        event_type: str,
        payload: dict,
        session: Optional[Any] = None,  # PlaySession instance
        step_index: int = 0,
        total_steps: int = 0,
        step_id: int = 0
    ) -> None:
        """
        Emit event with both UI and MCP metadata.
        
        Args:
            event_type: PLAY_STEP_START, FRAME, PLAY_DONE, etc.
            payload: Original payload for UI/FastAPI
            session: PlaySession for progress tracking
            step_index: Current step index (0-based)
            total_steps: Total steps in recording
            step_id: Step ID (1-based)
        """
        
        # Build base event
        event = {
            "type": event_type,
            "data": payload,  # Keep original for backward compatibility
            "timestamp": time.time()
        }
        
        # ✨ Add MCP response metadata if session provided
        if session:
            event["mcp_response"] = self._build_mcp_response(
                event_type=event_type,
                session=session,
                step_index=step_index,
                total_steps=total_steps,
                step_id=step_id,
                payload=payload
            )
        
        # Emit to all registered listeners
        for listener in self.listeners:
            try:
                await listener(event)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in event listener: {e}", exc_info=True)
    
    def _build_mcp_response(
        self,
        event_type: str,
        session: Any,
        step_index: int,
        total_steps: int,
        step_id: int,
        payload: dict
    ) -> Dict[str, Any]:
        """
        Build MCP response metadata for the event.
        This allows MCP clients to display progress without polling.
        """
        
        elapsed = session.get_elapsed_seconds() if hasattr(session, 'get_elapsed_seconds') else 0
        progress = int((step_index / total_steps) * 100) if total_steps > 0 else 0
        
        # Map event types to status codes and descriptions
        status_map = {
            "PLAY_STEP_START": ("executing", "STEP_RUNNING"),
            "PLAY_STEP_SKIPPED": ("skipped", "STEP_SKIPPED"),
            "PLAY_STEP_ERROR": ("error", "STEP_FAILED"),
            "FRAME": ("capturing", "FRAME_CAPTURED"),
            "PLAY_PAUSED": ("paused", "PAUSED"),
            "PLAY_DONE": ("completed", "COMPLETED"),
            "PLAY_ERROR": ("error", "PLAYBACK_FAILED"),
            "PLAY_ASSERTION_PASSED": ("completed", "ASSERTION_PASSED"),
        }
        
        status, status_code = status_map.get(event_type, ("unknown", "UNKNOWN"))
        
        # Build human-readable message
        message = self._build_message(event_type, step_id, total_steps, payload)
        
        return {
            "session_id": session.play_id if session else "unknown",
            "step_id": step_id,
            "step_index": step_index,
            "total_steps": total_steps,
            "status": status,
            "status_code": status_code,
            "message": message,
            "progress_percent": progress,
            "elapsed_seconds": round(elapsed, 2),
            "step_type": payload.get("type", "UNKNOWN"),
            # Additional MCP-specific fields
            "is_final_step": step_index == (total_steps - 1) if total_steps > 0 else False,
            "remaining_steps": max(0, total_steps - step_index - 1),
            # Extract coordinates if available
            "coordinates": payload.get("coords"),
            "error": payload.get("error"),
            "source": session.source if hasattr(session, 'source') else "unknown",
        }
    
    def _build_message(self, event_type: str, step_id: int, total_steps: int, payload: dict) -> str:
        """
        Build human-readable message for MCP display in CLI/chat.
        """
        
        step_num = step_id
        
        if event_type == "PLAY_STEP_START":
            step_type = payload.get("type", "UNKNOWN")
            if step_type == "CLICK":
                coords = payload.get("coords", {})
                x, y = coords.get("x", 0), coords.get("y", 0)
                return f"Step {step_num}/{total_steps}: Clicking at ({x}, {y})"
            elif step_type == "TYPE":
                text = payload.get("text", "")
                return f"Step {step_num}/{total_steps}: Typing '{text}'"
            elif step_type == "NAVIGATE":
                url = payload.get("url", "")
                return f"Step {step_num}/{total_steps}: Navigating to {url}"
            elif step_type == "SCROLL":
                dx = payload.get("dx", 0)
                dy = payload.get("dy", 0)
                return f"Step {step_num}/{total_steps}: Scrolling ({dx}, {dy})"
            elif step_type == "KEY":
                key = payload.get("key", "")
                return f"Step {step_num}/{total_steps}: Pressing {key}"
            elif step_type == "ASSERTION":
                assertion_type = payload.get("assertionType", "")
                return f"Step {step_num}/{total_steps}: Asserting {assertion_type}"
            else:
                return f"Step {step_num}/{total_steps}: {step_type}"
        
        elif event_type == "PLAY_STEP_SKIPPED":
            reason = payload.get("reason", "")
            return f"Step {step_num}: Skipped ({reason})"
        
        elif event_type == "PLAY_STEP_ERROR":
            error = payload.get("error", "Unknown error")
            return f"Step {step_num} FAILED: {error}"
        
        elif event_type == "PLAY_DONE":
            failed = payload.get("failedCount", 0)
            assertions_passed = payload.get("assertionPassed", 0)
            assertions_total = payload.get("assertionTotal", 0)
            if assertions_total > 0:
                return f"✅ Completed! {total_steps} steps, {failed} failures, {assertions_passed}/{assertions_total} assertions passed"
            else:
                return f"✅ Completed! {total_steps} steps executed, {failed} failures"
        
        elif event_type == "FRAME":
            return f"Step {step_num}/{total_steps}: Frame captured"
        
        elif event_type == "PLAY_PAUSED":
            reason = payload.get("reason", "")
            return f"Playback paused at step {step_num} ({reason})"
        
        elif event_type == "PLAY_ERROR":
            error = payload.get("error", "Unknown error")
            return f"❌ Playback error: {error}"
        
        elif event_type == "PLAY_ASSERTION_PASSED":
            assertion_type = payload.get("assertionType", "")
            return f"Assertion {assertion_type} passed"
        
        else:
            return f"{event_type}: Step {step_num}/{total_steps}"
    
    def on(self, callback: Callable) -> None:
        """
        Register an event listener.
        
        Args:
            callback: Async function that receives event dict
        """
        self.listeners.append(callback)
    
    def off(self, callback: Callable) -> None:
        """Remove an event listener."""
        try:
            self.listeners.remove(callback)
        except ValueError:
            pass
