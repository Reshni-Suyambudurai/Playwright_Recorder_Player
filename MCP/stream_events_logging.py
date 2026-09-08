"""
Stream live playback events from WebSocket with comprehensive logging.
Detailed logging at every step to diagnose connection and streaming issues.
"""
import asyncio
import json
import websockets
from pathlib import Path
import httpx
import sys
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

# ==================== LOGGING SETUP ====================
log_dir = Path(__file__).parent
log_file = log_dir / "stream_events.log"

# Create rotating logger
logger = logging.getLogger("stream_events")
logger.setLevel(logging.DEBUG)

# File handler - detailed logs
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# Console handler - info and above
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ==================== CONSTANTS ====================
BACKEND_URL = "http://localhost:8001"
WEBSOCKET_TIMEOUT = 60  # seconds
HTTP_TIMEOUT = 30  # seconds

# ==================== CONFIGURATION ====================
# JSON file to execute for playback
JSON_FILE_TO_EXECUTE = "playwright.json"  # Change this to switch between recordings

# ==================== HELPERS ====================

def log_section(title: str):
    """Log a section header"""
    line = "=" * 80
    logger.info(f"\n{line}")
    logger.info(f"  {title}")
    logger.info(f"{line}\n")

async def load_recording(json_path: Path) -> Optional[Dict[str, Any]]:
    """Load recording JSON with detailed logging"""
    logger.info(f"[LOAD] Attempting to load recording from: {json_path}")
    
    if not json_path.exists():
        logger.error(f"[LOAD] ❌ File not found: {json_path}")
        return None
    
    try:
        content = json_path.read_text(encoding='utf-8')
        logger.debug(f"[LOAD] File size: {len(content)} bytes")
        
        recording = json.loads(content)
        logger.info(f"[LOAD] ✓ Successfully parsed JSON")
        
        # Log recording structure
        if isinstance(recording, dict):
            logger.debug(f"[LOAD] Recording keys: {list(recording.keys())}")
            if 'steps' in recording:
                steps_info = recording['steps']
                if isinstance(steps_info, dict):
                    logger.debug(f"[LOAD] Steps is dict with keys: {list(steps_info.keys())}")
                    total_steps = sum(len(v) if isinstance(v, list) else 0 for v in steps_info.values())
                    logger.info(f"[LOAD] Total steps found: {total_steps}")
                elif isinstance(steps_info, list):
                    logger.info(f"[LOAD] Total steps found: {len(steps_info)}")
        
        return recording
    
    except json.JSONDecodeError as e:
        logger.error(f"[LOAD] ❌ JSON parsing failed: {e}")
        return None
    except Exception as e:
        logger.error(f"[LOAD] ❌ Unexpected error: {e}", exc_info=True)
        return None

async def start_playback(recording: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call backend to start playback with detailed logging"""
    log_section("STARTING PLAYBACK VIA BACKEND")
    
    request_body = {
        "recording_json": recording,
        "source": "mcp",
        "headless": False,
        "capture_frames": False  # MCP: metadata streaming only, no frame capture
    }
    
    logger.info(f"[HTTP] Backend URL: {BACKEND_URL}")
    logger.info(f"[HTTP] Endpoint: POST /play/start")
    logger.debug(f"[HTTP] Request body keys: {list(request_body.keys())}")
    logger.debug(f"[HTTP] Request timeout: {HTTP_TIMEOUT}s")
    
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            logger.debug(f"[HTTP] Creating POST request...")
            response = await client.post(
                f"{BACKEND_URL}/play/start",
                json=request_body
            )
            
            logger.info(f"[HTTP] ✓ Response received (status: {response.status_code})")
            logger.debug(f"[HTTP] Response headers: {dict(response.headers)}")
            
            # Log response body
            response_text = response.text
            logger.debug(f"[HTTP] Response body size: {len(response_text)} bytes")
            
            if response.status_code != 200:
                logger.error(f"[HTTP] ❌ Status {response.status_code}: {response_text}")
                return None
            
            result = response.json()
            logger.info(f"[HTTP] ✓ Response parsed successfully")
            logger.debug(f"[HTTP] Response keys: {list(result.keys())}")
            logger.info(f"[HTTP] ✓ Response: {json.dumps(result, indent=2)}")
            
            # Validate response
            if 'play_session_id' not in result:
                logger.error(f"[HTTP] ❌ Missing 'play_session_id' in response")
                logger.debug(f"[HTTP] Received: {result}")
                return None
            
            play_session_id = result['play_session_id']
            logger.info(f"[HTTP] ✓ play_session_id: {play_session_id}")
            
            # ✨ Log total steps (MCP mode)
            if 'total_steps' in result:
                total_steps = result['total_steps']
                logger.info(f"[HTTP] ✓ total_steps: {total_steps} (MCP live streaming)")
            
            if 'websocket_uri' in result:
                logger.info(f"[HTTP] ✓ websocket_uri: {result['websocket_uri']}")
            
            logger.info(f"[HTTP] ✓ Playback started successfully")
            return result
    
    except httpx.ConnectError as e:
        logger.error(f"[HTTP] ❌ Connection failed: {e}")
        logger.error(f"[HTTP] Is backend running at {BACKEND_URL}?")
        return None
    except httpx.TimeoutException as e:
        logger.error(f"[HTTP] ❌ Request timeout after {HTTP_TIMEOUT}s: {e}")
        return None
    except Exception as e:
        logger.error(f"[HTTP] ❌ Unexpected error: {e}", exc_info=True)
        return None

async def stream_events_websocket(websocket_uri: str) -> bool:
    """Connect to WebSocket and stream events with detailed logging"""
    log_section("WEBSOCKET CONNECTION & EVENT STREAMING")
    
    logger.info(f"[WS] WebSocket URI: {websocket_uri}")
    logger.info(f"[WS] Timeout per event: {WEBSOCKET_TIMEOUT}s")
    
    try:
        logger.debug(f"[WS] Initiating WebSocket connection...")
        async with websockets.connect(websocket_uri) as websocket:
            logger.info(f"[WS] ✓ WebSocket connection established")
            logger.debug(f"[WS] Connection state: OPEN")
            
            #  Send HELLO message to trigger playback task
            client_id = str(uuid.uuid4())
            hello_message = {
                "event_type": "HELLO",
                "data": {
                    "client_id": client_id
                }
            }
            logger.info(f"[WS] Sending HELLO message to start playback...")
            logger.debug(f"[WS] HELLO payload: {hello_message}")
            await websocket.send(json.dumps(hello_message))
            logger.info(f"[WS] ✓ HELLO message sent (client_id: {client_id})")
            print("✓ Sent HELLO message to start playback\n")
            
            event_count = 0
            start_time = datetime.now()
            
            logger.info(f"[WS] Waiting for events...")
            print("=" * 80)
            print("📡 STREAMING EVENTS (MCP FORMAT)")
            print("=" * 80 + "\n")
            
            while True:
                try:
                    logger.debug(f"[WS] Waiting for next event (timeout: {WEBSOCKET_TIMEOUT}s)...")
                    message = await asyncio.wait_for(websocket.recv(), timeout=WEBSOCKET_TIMEOUT)
                    
                    event_count += 1
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    logger.debug(f"[WS] Event #{event_count} received at {elapsed:.2f}s")
                    logger.debug(f"[WS] Message size: {len(message)} bytes")
                    
                    # Parse event
                    try:
                        event = json.loads(message)
                        logger.debug(f"[WS] ✓ Event parsed as JSON")
                    except json.JSONDecodeError as e:
                        logger.warning(f"[WS] ⚠ Failed to parse as JSON: {e}")
                        logger.debug(f"[WS] Raw message: {message}")
                        event = {"raw": message}
                    
                    # Log event structure
                    event_type = event.get('event_type', 'UNKNOWN')
                    event_data = event.get('data', {})
                    
                    logger.debug(f"[WS] Event type: {event_type}")
                    logger.debug(f"[WS] Event keys: {list(event.keys())}")
                    if isinstance(event_data, dict):
                        logger.debug(f"[WS] Event data keys: {list(event_data.keys())}")
                    
                    # ✅ Output raw JSON event to console (FRAME events not sent with capture_frames=False)
                    if event_type != 'FRAME':
                        print(json.dumps(event))
                    
                    # Log important events to file only
                    if event_type == 'WELCOME':
                        logger.info(f"[EVENT] WELCOME: Playback session ready")
                    
                    elif event_type == 'PLAY_STEP_START':
                        step_id = event_data.get('stepId')
                        idx = event_data.get('index')
                        total = event_data.get('total')
                        step_type = event_data.get('type')
                        page_title = event_data.get('pageTitle')
                        
                        # ✨ Log live streaming step with metadata
                        progress = f"{idx+1}/{total}" if idx is not None and total is not None else "?"
                        metadata_str = f"type={step_type}"
                        if page_title:
                            metadata_str += f", page={page_title}"
                        
                        logger.info(f"[STREAM] step {progress} — {metadata_str}")
                        
                        # Format console output
                        progress_pct = int(((idx or 0) / (total or 1)) * 100) if total else 0
                        print(f"[{progress}] {step_type.upper():<12} — {page_title or 'unknown'} ({progress_pct}%)")
                    
                    elif event_type == 'FRAME':
                        pass  # FRAME events not sent to MCP (capture_frames=False)
                    
                    elif event_type == 'PLAY_PAUSED':
                        step_id = event_data.get('stepId')
                        logger.warning(f"[EVENT] ⚠ PLAY_PAUSED at stepId={step_id}")
                        print(f"\n⚠ Playback paused at step {step_id} - waiting for user input\n")
                    
                    elif event_type == 'ERROR':
                        error_msg = event_data.get('error', 'Unknown error')
                        logger.error(f"[EVENT] ❌ ERROR: {error_msg}")
                    
                    elif event_type == 'DONE' or event_type == 'PLAY_DONE':
                        step_count = event_data.get('stepCount', event_count)
                        failed_count = event_data.get('failedCount', 0)
                        assertion_passed = event_data.get('assertionPassed', 0)
                        assertion_total = event_data.get('assertionTotal', 0)
                        
                        logger.info(f"[STREAM] ✅ Playback completed: {step_count} steps, {failed_count} failed, assertions {assertion_passed}/{assertion_total}")
                        print(f"\n✅ SUCCESS: Playback completed")
                        print(f"   - Steps: {step_count}")
                        print(f"   - Failed: {failed_count}")
                        print(f"   - Assertions: {assertion_passed}/{assertion_total} passed")
                        print(f"   - Duration: {elapsed:.2f}s\n")
                        return True
                    
                    else:
                        logger.debug(f"[EVENT] Event type: {event_type}")
                    
                except asyncio.TimeoutError:
                    logger.warning(f"[WS] ⚠ No events for {WEBSOCKET_TIMEOUT}s - timeout")
                    print(f"\n⏱ No events for {WEBSOCKET_TIMEOUT}s - connection stale\n")
                    return False
                
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"[WS] ⚠ WebSocket connection closed: {e}")
                    logger.info(f"[WS] Received {event_count} events before close")
                    return event_count > 0
                
                except Exception as e:
                    logger.error(f"[WS] ❌ Error processing event: {e}", exc_info=True)
                    return False
    
    except websockets.exceptions.InvalidURI as e:
        logger.error(f"[WS] ❌ Invalid WebSocket URI: {e}")
        return False
    
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"[WS] ❌ WebSocket error: {e}", exc_info=True)
        return False
    
    except Exception as e:
        logger.error(f"[WS] ❌ Unexpected error: {e}", exc_info=True)
        return False

async def main():
    """Main execution with comprehensive logging"""
    log_section("PLAYBACK STREAMING - START")
    logger.info(f"Process started at {datetime.now()}")
    logger.info(f"Log file: {log_file}")
    
    # Step 1: Load recording
    log_section("STEP 1: LOADING RECORDING")
    json_path = Path(__file__).parent / 'JSON' / JSON_FILE_TO_EXECUTE
    recording = await load_recording(json_path)
    
    if not recording:
        logger.error("[MAIN] ❌ Failed to load recording. Exiting.")
        return False
    
    # Step 2: Start playback
    log_section("STEP 2: START PLAYBACK")
    playback_result = await start_playback(recording)
    
    if not playback_result:
        logger.error("[MAIN] ❌ Failed to start playback. Exiting.")
        return False
    
    # Step 3: Stream events via WebSocket
    log_section("STEP 3: STREAM WEBSOCKET EVENTS")
    websocket_uri = playback_result.get('websocket_uri') or f"ws://localhost:8001/ws/play/{playback_result['play_session_id']}"
    success = await stream_events_websocket(websocket_uri)
    
    # Summary
    log_section("EXECUTION SUMMARY")
    logger.info(f"Recording file: {json_path}")
    logger.info(f"Backend: {BACKEND_URL}")
    logger.info(f"Play session ID: {playback_result['play_session_id']}")
    logger.info(f"WebSocket URI: {websocket_uri}")
    status_msg = '✅ SUCCESS - Playback completed successfully' if success else '❌ FAILED - Playback did not complete'
    logger.info(f"Status: {status_msg}")
    logger.info(f"Process ended at {datetime.now()}\n")
    
    # Print final status to console
    if success:
        print("=" * 80)
        print("✅ SUCCESS - Streaming completed successfully")
        print("=" * 80)
    else:
        print("=" * 80)
        print("❌ FAILED - Streaming did not complete")
        print("=" * 80)
    
    return success

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🎬 PLAYWRIGHT RECORDER - WEBSOCKET STREAMING WITH LOGGING")
    print("=" * 80)
    print(f"Log file: {log_file}\n")
    
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("[MAIN] ⏹ Interrupted by user")
        print("\n⏹ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"[MAIN] ❌ Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
