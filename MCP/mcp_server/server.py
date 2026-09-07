"""
MCP Server — Model Context Protocol v2 server for Playwright playback.
Production-grade thin proxy that routes tool calls to FastAPI backend via HTTP.

Communication: stdin/stdout JSON-RPC 2.0
Backend: HTTP calls to FastAPI (default: http://localhost:8001)
No local services - everything proxied to backend.
"""
import logging
import uuid
from typing import Dict

import httpx
from mcp.server import MCPServer

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp_server")



# Initialize MCPServer with v2 API
mcp = MCPServer("playback-mcp", log_level="DEBUG")


class PlaybackProxy:
    """Session management and HTTP proxy for Playwright playback."""
    
    def __init__(self, backend_url: str = "http://localhost:8001"):
        self.backend_url = backend_url.rstrip("/")
        self.http_client = httpx.AsyncClient(timeout=30.0)
        # Map MCP session ID → Backend play_id
        self.session_map: Dict[str, str] = {}
        logger.info(f"PlaybackProxy initialized (backend: {self.backend_url})")
    
    def _get_websocket_uri(self, play_id: str) -> str:
        """Convert HTTP backend URL to WebSocket URI."""
        ws_base = self.backend_url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{ws_base}/ws/play/{play_id}"
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()
        logger.info("HTTP client closed")


# Global proxy instance (initialized in run_mcp.py)
proxy: PlaybackProxy | None = None


def init_proxy(backend_url: str = "http://localhost:8001") -> PlaybackProxy:
    """Initialize the global proxy with the specified backend URL."""
    global proxy
    proxy = PlaybackProxy(backend_url)
    return proxy


@mcp.tool()
async def start_playback(recording_json: dict) -> dict:
    """
    Start a new playback session.
    
    This tool takes a recording JSON object and begins playback on the backend
    Playwright browser. Returns session details including WebSocket URI for
    real-time event streaming.
    
    Args:
        recording_json: Full recording object with 'steps' array.
                       Example: {"steps": [...], "title": "My Recording"}
    
    Returns:
        dict with:
        - mcp_session_id: UUID for this MCP session (use for stop_playback)
        - play_id: Backend playback ID (reference only)
        - websocket_uri: WebSocket URL for real-time event streaming
        - status: "started" on success
        - message: Human-readable status message
    
    Raises:
        ValueError: If recording_json is invalid or backend is unreachable
    """
    # Validate input
    if not isinstance(recording_json, dict):
        raise ValueError("recording_json must be a dictionary")
    
    if "steps" not in recording_json:
        raise ValueError("recording_json must have 'steps' key containing array of steps")
    
    if not isinstance(recording_json.get("steps"), list):
        raise ValueError("recording_json['steps'] must be an array")
    
    try:
        # Call backend /play/start endpoint with MCP-specific flags
        logger.info(f"Calling backend: POST {proxy.backend_url}/play/start")
        response = await proxy.http_client.post(
            f"{proxy.backend_url}/play/start",
            json={
                "recording_json": recording_json,
                "source": "mcp",
                "headless": False,
                "capture_frames": False
            },
        )
        response.raise_for_status()
        backend_response = response.json()
        logger.info(f"Backend response: {backend_response}")
        
        # ✅ Check if backend returned an error in response
        if "detail" in backend_response:
            error_msg = backend_response.get("detail", "Unknown error from backend")
            logger.error(f"[ERROR] Backend returned error: {error_msg}")
            raise ValueError(f"Backend error: {error_msg}")
        
        # ✅ Extract play_session_id from backend response (FIXED: was play_id)
        play_session_id = backend_response.get("play_session_id")
        if not play_session_id:
            error_msg = f"Backend did not return play_session_id. Received: {backend_response}"
            logger.error(f"[ERROR] {error_msg}")
            raise ValueError(error_msg)
        
        # Generate unique MCP session ID
        mcp_session_id = str(uuid.uuid4())
        
        # Store mapping for later lookups
        proxy.session_map[mcp_session_id] = play_session_id
        
        logger.info(
            f"✓ Started playback: mcp_session_id={mcp_session_id}, "
            f"backend_play_id={play_session_id}"
        )
        
        return {
            "mcp_session_id": mcp_session_id,
            "play_session_id": play_session_id,
            "websocket_uri": proxy._get_websocket_uri(play_session_id),
            "status": "started",
            "message": "Playback session started. Connect to WebSocket URI for real-time events.",
        }
    
    except httpx.TimeoutException as e:
        error_msg = f"Backend timeout (30s): {e}"
        logger.error(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    except httpx.ConnectError as e:
        error_msg = f"Cannot connect to backend at {proxy.backend_url}: {e}"
        logger.error(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    except httpx.HTTPError as e:
        status_code = e.response.status_code if hasattr(e, 'response') else 'unknown'
        error_msg = f"Backend HTTP error (status {status_code}): {e}"
        logger.error(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    except ValueError:
        # Re-raise ValueError (already logged above)
        raise
    
    except Exception as e:
        error_msg = f"Unexpected error in start_playback: {str(e)}"
        logger.error(f"[ERROR] {error_msg}", exc_info=True)
        raise ValueError(error_msg)


@mcp.tool()
async def stop_playback(mcp_session_id: str) -> dict:
    """
    Stop an active playback session.
    
    This tool stops a playback that was started with start_playback.
    The backend will close the browser and clean up resources.
    
    Args:
        mcp_session_id: The session ID returned by start_playback
    
    Returns:
        dict with:
        - status: "stopped" on success
        - mcp_session_id: The session ID that was stopped
        - message: Human-readable status message
    
    Raises:
        ValueError: If session not found or backend error occurs
    """
    # Validate input
    if not mcp_session_id or not isinstance(mcp_session_id, str):
        raise ValueError("mcp_session_id must be a non-empty string")
    
    # Lookup backend play_id from session mapping
    play_id = proxy.session_map.get(mcp_session_id)
    if not play_id:
        raise ValueError(
            f"Session {mcp_session_id} not found. "
            "Has it been started or already stopped?"
        )
    
    try:
        # Call backend DELETE /play/{play_session_id}
        logger.info(f"Calling backend: DELETE {proxy.backend_url}/play/{play_id}")
        response = await proxy.http_client.delete(
            f"{proxy.backend_url}/play/{play_id}",
        )
        response.raise_for_status()
        backend_response = response.json()
        logger.info(f"Backend stop response: {backend_response}")
        
        # ✅ Check if backend returned an error in response
        if "detail" in backend_response:
            error_msg = backend_response.get("detail", "Unknown error from backend")
            logger.error(f"[ERROR] Backend returned error on stop: {error_msg}")
            raise ValueError(f"Backend error: {error_msg}")
        
        # ✅ Verify success response
        if not backend_response.get("success"):
            error_msg = f"Backend failed to stop playback. Response: {backend_response}"
            logger.error(f"[ERROR] {error_msg}")
            raise ValueError(error_msg)
        
        # Clean up session mapping
        del proxy.session_map[mcp_session_id]
        
        logger.info(
            f"✓ Stopped playback: mcp_session_id={mcp_session_id}, "
            f"backend_play_id={play_id}"
        )
        
        return {
            "status": "stopped",
            "mcp_session_id": mcp_session_id,
            "message": "Playback session stopped successfully.",
        }
    
    except httpx.TimeoutException as e:
        error_msg = f"Backend timeout (30s) during stop: {e}"
        logger.error(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    except httpx.ConnectError as e:
        error_msg = f"Cannot connect to backend at {proxy.backend_url} during stop: {e}"
        logger.error(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    except httpx.HTTPError as e:
        status_code = e.response.status_code if hasattr(e, 'response') else 'unknown'
        error_msg = f"Backend HTTP error during stop (status {status_code}): {e}"
        logger.error(f"[ERROR] {error_msg}")
        raise ValueError(error_msg)
    
    except ValueError:
        # Re-raise ValueError (already logged and printed above)
        raise
    
    except Exception as e:
        error_msg = f"Unexpected error in stop_playback: {str(e)}"
        logger.error(f"[ERROR] {error_msg}", exc_info=True)
        raise ValueError(error_msg)

if __name__ == "__main__":
    # Run as subprocess (stdio transport - default)
    logger.info("Starting MCP server (stdio transport)")
    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

