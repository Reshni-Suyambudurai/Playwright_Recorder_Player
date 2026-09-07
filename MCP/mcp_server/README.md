# MCP v2 Playback Server

Production-grade Model Context Protocol v2.1.1+ server for Playwright playback automation.

## Overview

This is a **thin proxy** MCP server that routes playback requests to a FastAPI backend via HTTP. The server uses the high-level MCPServer API with `@mcp.tool()` decorators - no manual schema definition required.

```
┌──────────────────┐          JSON-RPC 2.0           ┌────────────────┐
│   MCP Client     │◄─────────  stdio  ────────────►│  MCP Server    │
│  (Claude, etc)   │                                 │  (thin proxy)  │
└──────────────────┘                                 └────────────────┘
                                                              │
                                                              │ HTTP
                                                              │
                                                     ┌────────────────┐
                                                     │ FastAPI Backend│
                                                     │  (Playwright)  │
                                                     └────────────────┘
```

## Architecture

### Stack
- **MCP**: `v2.1.1+` (Model Context Protocol)
- **Transport**: stdin/stdout (JSON-RPC 2.0)
- **Backend Communication**: HTTP (async httpx)
- **Python**: 3.10+

### Key Components

1. **`mcp_server/server.py`**: Main server module
   - `MCPServer("playback-mcp")`: High-level MCP v2 API
   - `@mcp.tool()` decorated functions: `start_playback()`, `stop_playback()`
   - `PlaybackProxy`: Session mapping and HTTP client management
   - Comprehensive error handling and logging

2. **`mcp_server/run_mcp.py`**: Startup script
   - Logging configuration (stderr + rotating file)
   - Environment variable support for backend URL

3. **`test_mcp_server.py`**: Unit tests (6 tests)
   - Server initialization
   - Tool decoration validation
   - Proxy functionality

4. **`test_mcp_integration.py`**: Integration tests (12 tests)
   - Mocked HTTP backend calls
   - Input validation
   - Error handling (timeout, connection errors, etc.)

## Quick Start

### Installation

```bash
cd backend/

# Install dependencies
pip install -r requirements.txt
# Requires: mcp>=2.1.1, httpx>=0.24.0, aiosqlite>=0.20.0
```

### Running the Server

```bash
# Default (backend at http://localhost:8001)
python mcp_server/run_mcp.py

# Custom backend URL
BACKEND_URL=http://localhost:9000 python mcp_server/run_mcp.py
```

The server listens on stdin/stdout for JSON-RPC 2.0 messages.

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest test_mcp_server.py test_mcp_integration.py -v

# Expected: 18 tests passed in ~1 second
```

## Tools

### 1. `start_playback`

**Purpose**: Start a new playback session

**Parameters**:
- `recording_json` (dict): Full recording object with `steps` array
  ```python
  {
    "steps": [
      {"action": "navigate", "url": "https://example.com"},
      {"action": "click", "selector": "button"},
      ...
    ],
    "title": "My Recording",
    ...other fields...
  }
  ```

**Returns**:
```python
{
  "mcp_session_id": "550e8400-e29b-41d4-a716-446655440000",  # Use for stop_playback
  "play_id": "play-12345",                                    # Backend ID
  "websocket_uri": "ws://localhost:8001/ws/play/play-12345",  # For real-time events
  "status": "started",
  "message": "Playback session started. Connect to WebSocket URI for real-time events."
}
```

**Error Handling**:
- `ValueError` if `recording_json` is not a dict
- `ValueError` if `steps` key missing or not an array
- `ValueError` if backend timeout (30s)
- `ValueError` if backend connection refused
- `ValueError` if backend returns invalid response

### 2. `stop_playback`

**Purpose**: Stop an active playback session

**Parameters**:
- `mcp_session_id` (str): Session ID returned by `start_playback`

**Returns**:
```python
{
  "status": "stopped",
  "mcp_session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Playback session stopped successfully."
}
```

**Error Handling**:
- `ValueError` if `mcp_session_id` is empty or missing
- `ValueError` if session not found (already stopped or never started)
- `ValueError` if backend timeout
- `ValueError` if backend connection refused

## Session Management

The server maintains an in-memory session mapping:

```python
session_map: Dict[str, str] = {
  "mcp-uuid-1": "backend-play-id-1",
  "mcp-uuid-2": "backend-play-id-2",
  ...
}
```

- **MCP Session ID**: UUID generated when `start_playback` is called
- **Backend Play ID**: Returned by FastAPI backend `/play/start` endpoint
- **Cleanup**: Session mapping entry deleted when `stop_playback` succeeds

## Logging

### Configuration
- **Level**: DEBUG (all operations logged)
- **Output**: 
  - stderr (immediate visibility)
  - `mcp_server.log` (rotating, 10MB max, 5 backups)

### Log Examples
```
2026-09-07 12:07:21,233 - mcp_server - INFO - PlaybackProxy initialized (backend: http://localhost:8001)
2026-09-07 12:07:42 - mcp_server.server - DEBUG - Starting tool call: start_playback
2026-09-07 12:07:42 - mcp_server.server - INFO - Calling backend: POST http://localhost:8001/play/start
2026-09-07 12:07:42 - mcp_server.server - INFO - Started playback: mcp_session_id=550e8400, backend_play_id=play-12345
```

## Error Handling

### Input Validation
- All parameters type-checked
- `recording_json` structure validated
- `mcp_session_id` non-empty validation

### HTTP Error Handling
```python
# Timeout (30s)
except httpx.TimeoutException:
    raise ValueError("Backend is not responding (timeout after 30 seconds)")

# Connection refused
except httpx.ConnectError:
    raise ValueError(f"Cannot connect to backend at {url}")

# HTTP errors (4xx, 5xx)
except httpx.HTTPError:
    raise ValueError(f"Backend error: {error}")
```

### Session Errors
- Session not found → `ValueError: Session {id} not found. Has it been started or already stopped?`
- Missing play_id in response → `ValueError: Backend did not return play_id in response`

## Production Requirements

✅ **Completed**:
- [x] MCP v2.1.1+ with high-level MCPServer API
- [x] `@mcp.tool()` decorators (auto JSON schema from type hints)
- [x] Full async/await with httpx (no blocking calls)
- [x] Comprehensive input validation
- [x] Error handling for all HTTP errors and timeouts
- [x] Full type hints on all functions
- [x] Detailed docstrings (auto-generates tool descriptions)
- [x] Logging to stderr and rotating file
- [x] Session management and mapping
- [x] Unit tests (6 tests)
- [x] Integration tests with mocked httpx (12 tests)
- [x] Production-ready startup script
- [x] Environment variable configuration

## WebSocket Connection

After `start_playback` returns successfully:

1. Client connects to `websocket_uri` returned by tool
2. Backend streams events in real-time:
   - `FRAME`: Screenshot frame
   - `STEP`: Step execution
   - `ERROR`: Playback error
   - `DONE`: Playback complete

Example:
```python
import asyncio
import websockets
import json

async def connect():
    uri = "ws://localhost:8001/ws/play/play-12345"
    async with websockets.connect(uri) as ws:
        while True:
            event = await ws.recv()
            data = json.loads(event)
            print(f"Event: {data['type']} - {data}")
```

## Testing

### Unit Tests (6 tests)
```bash
pytest test_mcp_server.py -v
```
- Server initialization
- Tool decoration
- Proxy functionality
- WebSocket URI generation
- Session mapping

### Integration Tests (12 tests)
```bash
pytest test_mcp_integration.py -v
```
- Valid playback start
- Input validation (missing steps, invalid type)
- Error handling (timeout, connection errors)
- Valid playback stop
- Session lookup errors
- Backend response validation

### All Tests
```bash
pytest test_mcp_server.py test_mcp_integration.py -v
# Expected: 18 passed
```

## Troubleshooting

### Server Won't Start
```
Error: Cannot connect to backend at http://localhost:8001
→ Ensure FastAPI backend is running on the expected URL
→ Check BACKEND_URL environment variable
```

### Tools Not Available
```
MCP error: Unknown tool 'start_playback'
→ Check server.py has @mcp.tool() decorators
→ Verify MCPServer import: from mcp.server import MCPServer
→ MCP v1 API does NOT have @mcp.tool(); must use v2+
```

### Timeout Issues
```
ValueError: Backend is not responding (timeout after 30 seconds)
→ Backend is too slow or unresponsive
→ Check backend logs: python run.py
→ Increase timeout in PlaybackProxy.__init__(timeout=60.0)
```

### Session Not Found
```
ValueError: Session abc-123 not found
→ Session was never started with start_playback
→ Session was already stopped
→ MCP server process restarted (session_map cleared)
```

## API Reference

### Backend Endpoints (Proxied)

The MCP server makes these HTTP calls to the backend:

**Start Playback**:
```http
POST /play/start
Content-Type: application/json

{
  "recording_json": { "steps": [...] }
}

Response:
{
  "play_id": "play-12345"
}
```

**Stop Playback**:
```http
DELETE /play/{play_id}

Response:
Status 204 or 200
```

**Real-time Events**:
```
WebSocket /ws/play/{play_id}
Streams: FRAME, STEP, ERROR, DONE
```

## Files Structure

```
backend/
├── mcp_server/
│   ├── __init__.py              # Package marker, exports mcp & proxy
│   ├── server.py                # Main MCP v2 server (MCPServer + @mcp.tool())
│   └── run_mcp.py               # Startup script with logging
├── test_mcp_server.py           # Unit tests (6 tests)
├── test_mcp_integration.py      # Integration tests with mocks (12 tests)
├── requirements.txt             # Dependencies (mcp>=2.1.1, httpx, etc.)
└── mcp_server.log              # Rotating log file (created on first run)
```

## Deployment

### Docker
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY backend/ .
RUN pip install -r requirements.txt

ENV BACKEND_URL=http://backend:8001
CMD ["python", "mcp_server/run_mcp.py"]
```

### SystemD Service
```ini
[Unit]
Description=MCP Playback Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/mcp_server/run_mcp.py
Environment="BACKEND_URL=http://localhost:8001"
Restart=on-failure
StandardOutput=append:/var/log/mcp_server.log
StandardError=append:/var/log/mcp_server.log

[Install]
WantedBy=multi-user.target
```

## Version History

- **v2.1.1+**: Production-grade MCP v2 with @mcp.tool() decorators
  - High-level MCPServer API
  - Auto JSON schema generation
  - Built-in logging
  - Async everywhere
  - Error handling & validation
  - 18 comprehensive tests

## References

- [MCP Documentation](https://modelcontextprotocol.io)
- [Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [httpx Documentation](https://www.python-httpx.org)
- [FastAPI Backend](../main.py)
