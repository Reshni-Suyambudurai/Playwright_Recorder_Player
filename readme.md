# MCP Playback Server - Setup & Execution Guide

## Quick Start Checklist

✅ Copy `mcp_server` folder to project  
✅ Install: `pip install mcp>=2.1.1 httpx>=0.24.0 websockets>=12.0`  
✅ Start **Backend**: `python backend/main.py` (on port 8001)  
✅ Start **MCP Server**: `python mcp_server/run_mcp.py` (stdio transport)  
✅ Connect to Claude or run test client  
✅ Use playback tools: `start_playback`, `stop_playback`  

---

## Proper Execution Order

### Step 1: Start the Backend
```bash
# Terminal 1 - Backend server
cd d:\KANINI_INTERN\My_Projects\Agent_TS\Automation_Agent
python backend/main.py
```
**Expected output:**
```
INFO:     Started server process [1234]
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### Step 2: Start MCP Server
```bash
# Terminal 2 - MCP server
cd d:\KANINI_INTERN\My_Projects\Agent_TS\Automation_Agent
python mcp_server/run_mcp.py
```
**Expected output:**
```
[2026-09-07 15:48:04,182] mcp_server.run_mcp - INFO - 
======================================================================
[2026-09-07 15:48:04,182] mcp_server.run_mcp - INFO - MCP Playback Server v2 (Thin Proxy)
[2026-09-07 15:48:04,182] mcp_server.run_mcp - INFO - Backend URL: http://localhost:8001
[2026-09-07 15:48:04,182] mcp_server.run_mcp - INFO - MCP Protocol: stdin/stdout (JSON-RPC 2.0)
[2026-09-07 15:48:04,182] mcp_server.run_mcp - INFO - Tools: start_playback, stop_playback
======================================================================
```

### Step 3: Execute Playback
```bash
# Terminal 3 - Test client
python call_mcp.py
```

---

## Log File Monitoring

All requests, responses, and errors are logged to **`mcp_server.log`**

### Watch logs in real-time:
```bash
# PowerShell - Tail log file
Get-Content mcp_server.log -Tail 50 -Wait
```

### Log sections:
- **REQUEST**: POST/DELETE calls to backend with full payload
- **RESPONSE**: HTTP status and backend response data
- **ERRORS**: Connection, timeout, validation errors with troubleshooting hints

---

## Troubleshooting

### ❌ Connection Refused (Port 8001)
**Problem**: "Cannot connect to backend at http://localhost:8001"

**Check:**
1. Backend is running on correct port
   ```bash
   netstat -ano | findstr :8001
   ```
2. Start backend:
   ```bash
   python backend/main.py
   ```
3. Verify backend is accessible:
   ```bash
   curl http://localhost:8001/openapi.json
   ```

### ❌ Backend Timeout (30s)
**Problem**: "Backend is not responding (timeout after 30 seconds)"

**Check:**
1. Is backend process still running?
   ```bash
   Get-Process python | Where-Object {$_.CommandLine -match "backend"}
   ```
2. Check backend logs for errors
3. Restart backend:
   ```bash
   # Kill old process
   Stop-Process -Name python -Force
   # Start fresh
   python backend/main.py
   ```

### ❌ WebSocket 404 Error
**Problem**: "server rejected WebSocket connection: HTTP 404"

**Possible causes:**
1. Playback not started (call `start_playback` first)
2. Play session ID is invalid or expired
3. WebSocket endpoint not implemented in backend

**Solution:**
- Check `mcp_server.log` for WebSocket URI details
- Verify backend supports `/ws/play/{play_id}` endpoint
- Check backend implementation

### ❌ Module Import Error
**Problem**: "ModuleNotFoundError: No module named 'mcp_server'"

**Fix:**
- Ensure you're in workspace root directory
- Check `mcp_server/run_mcp.py` has sys.path setup:
  ```python
  backend_dir = Path(__file__).parent.parent
  sys.path.insert(0, str(backend_dir))
  ```

### ❌ Steps Validation Error
**Problem**: "recording_json['steps'] must be an array"

**Check:**
- UWH.json format: steps can be dict or array
- Server was updated to accept both formats
- Look in logs: `mcp_server.log` for details

---

## MCP Request/Response Flow

```
User/Client
    ↓
call_mcp.py (stdio MCP client)
    ↓
mcp_server/run_mcp.py (stdio transport)
    ↓
mcp_server/server.py (MCP tools)
    ↓
HTTP POST/DELETE
    ↓
backend/main.py (FastAPI server on :8001)
    ↓
Response JSON
    ↓
[LOGGED TO: mcp_server.log]
    ↓
Return to user/client
```

---

## Log File Format

Each operation is logged with clear sections:

```log
======================================================================
REQUEST: POST http://localhost:8001/play/start
Recording: uwh upd 90
Steps count: 29
Full payload: {...}
======================================================================

======================================================================
RESPONSE: HTTP 200 OK
Backend Response: {'play_session_id': '4e6432a0-a716-428d-9e03-d067bbf99750'}
======================================================================

======================================================================
✓ PLAYBACK STARTED SUCCESSFULLY
  MCP Session ID: 0dea9e6d-13c5-433e-8f44-045508e731bc
  Backend Play ID: 4e6432a0-a716-428d-9e03-d067bbf99750
  WebSocket URI: ws://localhost:8001/ws/play/4e6432a0-a716-428d-9e03-d067bbf99750
  Status: started
======================================================================
```

---

## Environment Configuration

### Custom Backend URL
```bash
# Default backend URL is http://localhost:8001
# Override with environment variable:
$env:BACKEND_URL = "http://localhost:9000"
python mcp_server/run_mcp.py
```

### Logging Levels
- **DEBUG**: Full request/response details, timestamps
- **INFO**: MCP server startup, successful calls, session tracking
- **ERROR**: Connection errors, timeouts, validation failures

---

## Testing

### Test playback execution:
```bash
python call_mcp.py
```

### Test WebSocket connection:
```bash
python stream_events_v2.py
```

### View real-time logs:
```bash
Get-Content mcp_server.log -Tail 50 -Wait
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `mcp_server/run_mcp.py` | MCP server startup & logging setup |
| `mcp_server/server.py` | Tool implementations, HTTP proxy |
| `call_mcp.py` | Test client (stdio MCP) |
| `stream_events_v2.py` | WebSocket event streaming |
| `mcp_server.log` | All request/response/error logs |
| `JSON/UWH.json` | Playwright recording (29 steps) |

---

## Next Steps

1. ✅ Start backend server
2. ✅ Start MCP server (watch for startup logs)
3. ✅ Run test client
4. ✅ Monitor `mcp_server.log` for request/response details
5. 🔄 Stream WebSocket events (once endpoint is ready)
